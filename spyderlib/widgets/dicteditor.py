# -*- coding: utf-8 -*-
#
# Copyright © 2009-2010 Pierre Raybaut
# Licensed under the terms of the MIT License
# (see spyderlib/__init__.py for details)

"""
Dictionary Editor Widget and Dialog based on Qt
"""

#TODO: Multiple selection: open as many editors (array/dict/...) as necessary,
#      at the same time

# pylint: disable=C0103
# pylint: disable=R0903
# pylint: disable=R0911
# pylint: disable=R0201

import os, sys, datetime
from spyderlib.qt.QtGui import (QMessageBox, QTableView, QItemDelegate,
                                QLineEdit, QVBoxLayout, QWidget, QColor,
                                QDialog, QDateEdit, QDialogButtonBox, QMenu,
                                QInputDialog, QDateTimeEdit, QApplication,
                                QKeySequence)
from spyderlib.qt.QtCore import (Qt, QModelIndex, QAbstractTableModel, SIGNAL,
                                 SLOT, QDateTime, Signal)
from spyderlib.qt.compat import to_qvariant, from_qvariant, getsavefilename

# Local import
from spyderlib.baseconfig import _
from spyderlib.config import get_icon, get_font
from spyderlib.utils.misc import fix_reference_name
from spyderlib.utils.qthelpers import add_actions, create_action, qapplication
from spyderlib.widgets.dicteditorutils import (sort_against, get_size,
                   get_type, value_to_display, get_color_name, is_known_type,
                   FakeObject, Image, ndarray, array, PIL, unsorted_unique,
                   try_to_eval, datestr_to_datetime, get_numpy_dtype)
if ndarray is not FakeObject:
    from spyderlib.widgets.arrayeditor import ArrayEditor
from spyderlib.widgets.texteditor import TextEditor
from spyderlib.widgets.importwizard import ImportWizard


def display_to_value(value, default_value, ignore_errors=True):
    """Convert back to value"""
    value = from_qvariant(value, unicode)
    try:
        np_dtype = get_numpy_dtype(default_value)
        if isinstance(default_value, bool):
            # We must test for boolean before NumPy data types
            # because `bool` class derives from `int` class
            try:
                value = bool(float(value))
            except ValueError:
                value = value.lower() == "true"
        elif np_dtype is not None:
            if 'complex' in str(type(default_value)):
                value = np_dtype(complex(value))
            else:
                value = np_dtype(value)
        elif isinstance(default_value, str):
            value = str(value)
        elif isinstance(default_value, unicode):
            value = unicode(value)
        elif isinstance(default_value, complex):
            value = complex(value)
        elif isinstance(default_value, float):
            value = float(value)
        elif isinstance(default_value, int):
            try:
                value = int(value)
            except ValueError:
                value = float(value)
        elif isinstance(default_value, datetime.datetime):
            value = datestr_to_datetime(value)
        elif isinstance(default_value, datetime.date):
            value = datestr_to_datetime(value).date()
        elif ignore_errors:
            value = try_to_eval(value)
        else:
            value = eval(value)
    except (ValueError, SyntaxError):
        if ignore_errors:
            value = try_to_eval(value)
        else:
            raise
    return value


class ReadOnlyDictModel(QAbstractTableModel):
    """DictEditor Read-Only Table Model"""
    def __init__(self, parent, data, title="", names=False,
                 truncate=True, minmax=False, collvalue=True, remote=False):
        QAbstractTableModel.__init__(self, parent)
        if data is None:
            data = {}
        self.names = names
        self.truncate = truncate
        self.minmax = minmax
        self.collvalue = collvalue
        self.remote = remote
        self.header0 = None
        self._data = None
        self.showndata = None
        self.keys = None
        self.title = unicode(title) # in case title is not a string
        if self.title:
            self.title = self.title + ' - '
        self.sizes = None
        self.types = None
        self.set_data(data)
        
    def get_data(self):
        """Return model data"""
        return self._data
            
    def set_data(self, data, dictfilter=None):
        """Set model data"""
        self._data = data
        if dictfilter is not None and not self.remote:
            data = dictfilter(data)
        self.showndata = data
        self.header0 = _("Index")
        if self.names:
            self.header0 = _("Name")
        if isinstance(data, tuple):
            self.keys = range(len(data))
            self.title += _("Tuple")
        elif isinstance(data, list):
            self.keys = range(len(data))
            self.title += _("List")
        elif isinstance(data, dict):
            self.keys = data.keys()
            self.title += _("Dictionary")
            if not self.names:
                self.header0 = _("Key")
        else:
            raise TypeError("Invalid data type")
        self.title += ' ('+str(len(self.keys))+' '+ _("elements")+')'
        if self.remote:
            self.sizes = [ data[self.keys[index]]['size']
                           for index in range(len(self.keys)) ]
            self.types = [ data[self.keys[index]]['type']
                           for index in range(len(self.keys)) ]
        else:
            self.sizes = [ get_size(data[self.keys[index]])
                           for index in range(len(self.keys)) ]
            self.types = [ get_type(data[self.keys[index]])
                           for index in range(len(self.keys)) ]
        self.reset()

    def sort(self, column, order=Qt.AscendingOrder):
        """Overriding sort method"""
        reverse = (order==Qt.DescendingOrder)
        if column == 0:
            self.sizes = sort_against(self.sizes, self.keys, reverse)
            self.types = sort_against(self.types, self.keys, reverse)
            self.keys.sort(reverse=reverse)
        elif column == 1:
            self.keys = sort_against(self.keys, self.types, reverse)
            self.sizes = sort_against(self.sizes, self.types, reverse)
            self.types.sort(reverse=reverse)
        elif column == 2:
            self.keys = sort_against(self.keys, self.sizes, reverse)
            self.types = sort_against(self.types, self.sizes, reverse)
            self.sizes.sort(reverse=reverse)
        elif column == 3:
            self.keys = sort_against(self.keys, self.sizes, reverse)
            self.types = sort_against(self.types, self.sizes, reverse)
            self.sizes.sort(reverse=reverse)
        elif column == 4:
            values = [self._data[key] for key in self.keys]
            self.keys = sort_against(self.keys, values, reverse)
            self.sizes = sort_against(self.sizes, values, reverse)
            self.types = sort_against(self.types, values, reverse)
        self.reset()

    def columnCount(self, qindex=QModelIndex()):
        """Array column number"""
        return 4

    def rowCount(self, qindex=QModelIndex()):
        """Array row number"""
        return len(self.keys)
    
    def get_index_from_key(self, key):
        try:
            return self.createIndex(self.keys.index(key), 0)
        except ValueError:
            return QModelIndex()
    
    def get_key(self, index):
        """Return current key"""
        return self.keys[index.row()]
    
    def get_value(self, index):
        """Return current value"""
        if index.column() == 0:
            return self.keys[ index.row() ]
        elif index.column() == 1:
            return self.types[ index.row() ]
        elif index.column() == 2:
            return self.sizes[ index.row() ]
        else:
            return self._data[ self.keys[index.row()] ]

    def get_bgcolor(self, index):
        """Background color depending on value"""
        if index.column() == 0:
            color = QColor(Qt.lightGray)
            color.setAlphaF(.05)
        elif index.column() < 3:
            color = QColor(Qt.lightGray)
            color.setAlphaF(.2)
        else:
            color = QColor(Qt.lightGray)
            color.setAlphaF(.3)
        return color

    def data(self, index, role=Qt.DisplayRole):
        """Cell content"""
        if not index.isValid():
            return to_qvariant()
        value = self.get_value(index)
        if index.column() == 3 and self.remote:
            value = value['view']
        display = value_to_display(value,
                               truncate=index.column() == 3 and self.truncate,
                               minmax=self.minmax,
                               collvalue=self.collvalue or index.column() != 3)
        if role == Qt.DisplayRole:
            return to_qvariant(display)
        elif role == Qt.EditRole:
            return to_qvariant(value_to_display(value))
        elif role == Qt.TextAlignmentRole:
            if index.column() == 3:
                if len(display.splitlines()) < 3:
                    return to_qvariant(int(Qt.AlignLeft|Qt.AlignVCenter))
                else:
                    return to_qvariant(int(Qt.AlignLeft|Qt.AlignTop))
            else:
                return to_qvariant(int(Qt.AlignLeft|Qt.AlignVCenter))
        elif role == Qt.BackgroundColorRole:
            return to_qvariant( self.get_bgcolor(index) )
        elif role == Qt.FontRole:
            if index.column() < 3:
                return to_qvariant(get_font('dicteditor_header'))
            else:
                return to_qvariant(get_font('dicteditor'))
        return to_qvariant()
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """Overriding method headerData"""
        if role != Qt.DisplayRole:
            if role == Qt.FontRole:
                return to_qvariant(get_font('dicteditor_header'))
            else:
                return to_qvariant()
        i_column = int(section)
        if orientation == Qt.Horizontal:
            headers = (self.header0, _("Type"), _("Size"), _("Value"))
            return to_qvariant( headers[i_column] )
        else:
            return to_qvariant()

    def flags(self, index):
        """Overriding method flags"""
        # This method was implemented in DictModel only, but to enable tuple
        # exploration (even without editing), this method was moved here
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemFlags(QAbstractTableModel.flags(self, index)|
                            Qt.ItemIsEditable)

class DictModel(ReadOnlyDictModel):
    """DictEditor Table Model"""
    
    def set_value(self, index, value):
        """Set value"""
        self._data[ self.keys[index.row()] ] = value
        self.showndata[ self.keys[index.row()] ] = value
        self.sizes[index.row()] = get_size(value)
        self.types[index.row()] = get_type(value)

    def get_bgcolor(self, index):
        """Background color depending on value"""
        value = self.get_value(index)
        if index.column() < 3:
            color = ReadOnlyDictModel.get_bgcolor(self, index)
        else:
            if self.remote:
                color_name = value['color']
            else:
                color_name = get_color_name(value)
            color = QColor(color_name)
            color.setAlphaF(.2)
        return color

    def setData(self, index, value, role=Qt.EditRole):
        """Cell content change"""
        if not index.isValid():
            return False
        if index.column() < 3:
            return False
        value = display_to_value(value, self.get_value(index),
                                 ignore_errors=True)
        self.set_value(index, value)
        self.emit(SIGNAL("dataChanged(QModelIndex,QModelIndex)"),
                  index, index)
        return True


class DictDelegate(QItemDelegate):
    """DictEditor Item Delegate"""
    def __init__(self, parent=None, inplace=False):
        QItemDelegate.__init__(self, parent)
        self.inplace = inplace
        self._editors = {} # keep references on opened editors
        
    def get_value(self, index):
        if index.isValid():
            return index.model().get_value(index)
    
    def set_value(self, index, value):
        if index.isValid():
            index.model().set_value(index, value)

    def createEditor(self, parent, option, index):
        """Overriding method createEditor"""
        if index.column() < 3:
            return None
        try:
            value = self.get_value(index)
        except Exception, msg:
            QMessageBox.critical(self.parent(), _("Edit item"),
                                 _("<b>Unable to retrieve data.</b>"
                                   "<br><br>Error message:<br>%s"
                                   ) % unicode(msg))
            return
        key = index.model().get_key(index)
        readonly = isinstance(value, tuple) or self.parent().readonly \
                   or not is_known_type(value)
        #---editor = DictEditor
        if isinstance(value, (list, tuple, dict)) and not self.inplace:
            editor = DictEditor()
            editor.setup(value, key, icon=self.parent().windowIcon(),
                         readonly=readonly)
            self.create_dialog(editor, dict(model=index.model(), editor=editor,
                                            key=key, readonly=readonly))
            return None
        #---editor = ArrayEditor
        elif isinstance(value, ndarray) and ndarray is not FakeObject \
                                        and not self.inplace:
            if value.size == 0:
                return None
            editor = ArrayEditor(parent)
            if not editor.setup_and_check(value, title=key, readonly=readonly):
                return
            self.create_dialog(editor, dict(model=index.model(), editor=editor,
                                            key=key, readonly=readonly))
            return None
        #---showing image
        elif isinstance(value, Image) and ndarray is not FakeObject \
             and Image is not FakeObject:
            arr = array(value)
            if arr.size == 0:
                return None
            editor = ArrayEditor(parent)
            if not editor.setup_and_check(arr, title=key, readonly=readonly):
                return
            conv_func = lambda arr: PIL.Image.fromarray(arr, mode=value.mode)
            self.create_dialog(editor, dict(model=index.model(), editor=editor,
                                            key=key, readonly=readonly,
                                            conv=conv_func))
            return None
        #---editor = QDateTimeEdit
        elif isinstance(value, datetime.datetime) and not self.inplace:
            editor = QDateTimeEdit(value, parent)
            editor.setCalendarPopup(True)
            editor.setFont(get_font('dicteditor'))
            self.connect(editor, SIGNAL("returnPressed()"),
                         self.commitAndCloseEditor)
            return editor
        #---editor = QDateEdit
        elif isinstance(value, datetime.date) and not self.inplace:
            editor = QDateEdit(value, parent)
            editor.setCalendarPopup(True)
            editor.setFont(get_font('dicteditor'))
            self.connect(editor, SIGNAL("returnPressed()"),
                         self.commitAndCloseEditor)
            return editor
        #---editor = QTextEdit
        elif isinstance(value, (str, unicode)) and len(value)>40:
            editor = TextEditor(value, key)
            self.create_dialog(editor, dict(model=index.model(), editor=editor,
                                            key=key, readonly=readonly))
            return None
        #---editor = QLineEdit
        else:
            editor = QLineEdit(parent)
            editor.setFont(get_font('dicteditor'))
            editor.setAlignment(Qt.AlignLeft)
            self.connect(editor, SIGNAL("returnPressed()"),
                         self.commitAndCloseEditor)
            return editor
            
    def create_dialog(self, editor, data):
        self._editors[id(editor)] = data
        self.connect(editor, SIGNAL('accepted()'),
                     lambda eid=id(editor): self.editor_accepted(eid))
        self.connect(editor, SIGNAL('rejected()'),
                     lambda eid=id(editor): self.editor_rejected(eid))
        editor.show()
        
    def editor_accepted(self, editor_id):
        data = self._editors[editor_id]
        if not data['readonly']:
            index = data['model'].get_index_from_key(data['key'])
            value = data['editor'].get_value()
            conv_func = data.get('conv', lambda v: v)
            self.set_value(index, conv_func(value))
        self._editors.pop(editor_id)
        
    def editor_rejected(self, editor_id):
        self._editors.pop(editor_id)

    def commitAndCloseEditor(self):
        """Overriding method commitAndCloseEditor"""
        editor = self.sender()
        self.emit(SIGNAL("commitData(QWidget*)"), editor)
        self.emit(SIGNAL("closeEditor(QWidget*)"), editor)

    def setEditorData(self, editor, index):
        """Overriding method setEditorData
        Model --> Editor"""
        value = self.get_value(index)
        if isinstance(editor, QLineEdit):
            if not isinstance(value, basestring):
                value = repr(value)
            editor.setText(value)
        elif isinstance(editor, QDateEdit):
            editor.setDate(value)
        elif isinstance(editor, QDateTimeEdit):
            editor.setDateTime(QDateTime(value.date(), value.time()))

    def setModelData(self, editor, model, index):
        """Overriding method setModelData
        Editor --> Model"""
        if not hasattr(model, "set_value"):
            # Read-only mode
            return
        
        if isinstance(editor, QLineEdit):
            value = editor.text()
            try:
                value = display_to_value(to_qvariant(value),
                                         self.get_value(index),
                                         ignore_errors=False)
            except Exception, msg:
                raise
                QMessageBox.critical(editor, _("Edit item"),
                                     _("<b>Unable to assign data to item.</b>"
                                       "<br><br>Error message:<br>%s"
                                       ) % str(msg))
                return
        elif isinstance(editor, QDateEdit):
            qdate = editor.date()
            value = datetime.date( qdate.year(), qdate.month(), qdate.day() )
        elif isinstance(editor, QDateTimeEdit):
            qdatetime = editor.dateTime()
            qdate = qdatetime.date()
            qtime = qdatetime.time()
            value = datetime.datetime( qdate.year(), qdate.month(),
                                       qdate.day(), qtime.hour(),
                                       qtime.minute(), qtime.second() )
        else:
            # Should not happen...
            raise RuntimeError("Unsupported editor widget")
        self.set_value(index, value)


class BaseTableView(QTableView):
    """Base dictionnary editor table view"""
    sig_option_changed = Signal(str, object)
    def __init__(self, parent):
        QTableView.__init__(self, parent)
        self.array_filename = None
        self.menu = None
        self.empty_ws_menu = None
        self.paste_action = None
        self.copy_action = None
        self.edit_action = None
        self.plot_action = None
        self.imshow_action = None
        self.save_array_action = None
        self.insert_action = None
        self.remove_action = None
        self.truncate_action = None
        self.minmax_action = None
        self.collvalue_action = None
        self.inplace_action = None
        self.rename_action = None
        self.duplicate_action = None
        self.delegate = None
        
    def setup_table(self):
        """Setup table"""
        self.horizontalHeader().setStretchLastSection(True)
        self.adjust_columns()
        # Sorting columns
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)
    
    def setup_menu(self, truncate, minmax, inplace, collvalue):
        """Setup context menu"""
        if self.truncate_action is not None:
            self.truncate_action.setChecked(truncate)
            self.minmax_action.setChecked(minmax)
            self.inplace_action.setChecked(inplace)
            self.collvalue_action.setChecked(collvalue)
            return
        
        self.paste_action = create_action(self, _("Paste"),
                                          icon=get_icon('editpaste.png'),
                                          triggered=self.paste)
        self.copy_action = create_action(self, _("Copy"),
                                         icon=get_icon('editcopy.png'),
                                         triggered=self.copy)                                      
        self.edit_action = create_action(self, _("Edit"),
                                         icon=get_icon('edit.png'),
                                         triggered=self.edit_item)
        self.plot_action = create_action(self, _("Plot"),
                                         icon=get_icon('plot.png'),
                                         triggered=self.plot_item)
        self.plot_action.setVisible(False)
        self.imshow_action = create_action(self, _("Show image"),
                                           icon=get_icon('imshow.png'),
                                           triggered=self.imshow_item)
        self.imshow_action.setVisible(False)
        self.save_array_action = create_action(self, _("Save array"),
                                               icon=get_icon('filesave.png'),
                                               triggered=self.save_array)
        self.save_array_action.setVisible(False)
        self.insert_action = create_action(self, _("Insert"),
                                           icon=get_icon('insert.png'),
                                           triggered=self.insert_item)
        self.remove_action = create_action(self, _("Remove"),
                                           icon=get_icon('editdelete.png'),
                                           triggered=self.remove_item)
        self.truncate_action = create_action(self, _("Truncate values"),
                                             toggled=self.toggle_truncate)
        self.truncate_action.setChecked(truncate)
        self.toggle_truncate(truncate)
        self.minmax_action = create_action(self, _("Show arrays min/max"),
                                           toggled=self.toggle_minmax)
        self.minmax_action.setChecked(minmax)
        self.toggle_minmax(minmax)
        self.collvalue_action = create_action(self,
                                              _("Show collection contents"),
                                              toggled=self.toggle_collvalue)
        self.collvalue_action.setChecked(collvalue)
        self.toggle_collvalue(collvalue)
        self.inplace_action = create_action(self, _("Always edit in-place"),
                                            toggled=self.toggle_inplace)
        self.inplace_action.setChecked(inplace)
        if self.delegate is None:
            self.inplace_action.setEnabled(False)
        else:
            self.toggle_inplace(inplace)
        self.rename_action = create_action(self, _( "Rename"),
                                           icon=get_icon('rename.png'),
                                           triggered=self.rename_item)
        self.duplicate_action = create_action(self, _( "Duplicate"),
                                              icon=get_icon('edit_add.png'),
                                              triggered=self.duplicate_item)
        menu = QMenu(self)
        menu_actions = [self.edit_action, self.plot_action, self.imshow_action,
                        self.save_array_action, self.insert_action,
                        self.remove_action, self.copy_action, self.paste_action,
                        None, self.rename_action,self.duplicate_action,
                        None, self.truncate_action, self.inplace_action,
                        self.collvalue_action]
        if ndarray is not FakeObject:
            menu_actions.append(self.minmax_action)
        add_actions(menu, menu_actions)
        self.empty_ws_menu = QMenu(self)
        add_actions(self.empty_ws_menu, [self.insert_action, self.paste_action])
        return menu
    
    #------ Remote/local API ---------------------------------------------------
    def remove_values(self, keys):
        """Remove values from data"""
        raise NotImplementedError

    def copy_value(self, orig_key, new_key):
        """Copy value"""
        raise NotImplementedError
    
    def new_value(self, key, value):
        """Create new value in data"""
        raise NotImplementedError
        
    def is_list(self, key):
        """Return True if variable is a list or a tuple"""
        raise NotImplementedError
        
    def get_len(self, key):
        """Return sequence length"""
        raise NotImplementedError
        
    def is_array(self, key):
        """Return True if variable is a numpy array"""
        raise NotImplementedError

    def is_image(self, key):
        """Return True if variable is a PIL.Image image"""
        raise NotImplementedError
    
    def is_dict(self, key):
        """Return True if variable is a dictionary"""
        raise NotImplementedError
        
    def get_array_shape(self, key):
        """Return array's shape"""
        raise NotImplementedError
        
    def get_array_ndim(self, key):
        """Return array's ndim"""
        raise NotImplementedError
    
    def oedit(self, key):
        """Edit item"""
        raise NotImplementedError
    
    def plot(self, key):
        """Plot item"""
        raise NotImplementedError
    
    def imshow(self, key):
        """Show item's image"""
        raise NotImplementedError
    
    def show_image(self, key):
        """Show image (item is a PIL image)"""
        raise NotImplementedError
    #---------------------------------------------------------------------------
            
    def refresh_menu(self):
        """Refresh context menu"""
        index = self.currentIndex()
        condition = index.isValid()
        self.edit_action.setEnabled( condition )
        self.remove_action.setEnabled( condition )
        self.refresh_plot_entries(index)
        
    def refresh_plot_entries(self, index):
        if index.isValid():
            key = self.model.get_key(index)
            is_list = self.is_list(key)
            is_array = self.is_array(key) and self.get_len(key) != 0
            condition_plot = (is_array and len(self.get_array_shape(key)) <= 2)
            condition_imshow = condition_plot and self.get_array_ndim(key) == 2
            condition_imshow = condition_imshow or self.is_image(key)
        else:
            is_array = condition_plot = condition_imshow = is_list = False
        self.plot_action.setVisible(condition_plot or is_list)
        self.imshow_action.setVisible(condition_imshow)
        self.save_array_action.setVisible(is_array)
        
    def adjust_columns(self):
        """Resize two first columns to contents"""
        for col in range(3):
            self.resizeColumnToContents(col)
        
    def set_data(self, data):
        """Set table data"""
        if data is not None:
            self.model.set_data(data, self.dictfilter)
            self.sortByColumn(0, Qt.AscendingOrder)

    def mousePressEvent(self, event):
        """Reimplement Qt method"""
        if event.button() != Qt.LeftButton:
            QTableView.mousePressEvent(self, event)
            return
        index_clicked = self.indexAt(event.pos())
        if index_clicked.isValid():
            if index_clicked == self.currentIndex() \
               and index_clicked in self.selectedIndexes():
                self.clearSelection()
            else:
                QTableView.mousePressEvent(self, event)
        else:
            self.clearSelection()
            event.accept()
    
    def mouseDoubleClickEvent(self, event):
        """Reimplement Qt method"""
        index_clicked = self.indexAt(event.pos())
        if index_clicked.isValid():
            self.edit_item()
        else:
            event.accept()
    
    def keyPressEvent(self, event):
        """Reimplement Qt methods"""
        if event.key() == Qt.Key_Delete:
            self.remove_item()
        elif event.key() == Qt.Key_F2:
            self.rename_item()
        elif event == QKeySequence.Copy:
            self.copy()
        elif event == QKeySequence.Paste:
            self.paste()
        else:
            QTableView.keyPressEvent(self, event)
        
    def contextMenuEvent(self, event):
        """Reimplement Qt method"""
        if self.model.showndata:
            self.refresh_menu()
            self.menu.popup(event.globalPos())
            event.accept()
        else:
            self.empty_ws_menu.popup(event.globalPos())
            event.accept()

    def toggle_inplace(self, state):
        """Toggle in-place editor option"""
        self.sig_option_changed.emit('inplace', state)
        self.delegate.inplace = state
        
    def toggle_truncate(self, state):
        """Toggle display truncating option"""
        self.sig_option_changed.emit('truncate', state)
        self.model.truncate = state
        
    def toggle_minmax(self, state):
        """Toggle min/max display for numpy arrays"""
        self.sig_option_changed.emit('minmax', state)
        self.model.minmax = state
        
    def toggle_collvalue(self, state):
        """Toggle value display for collections"""
        self.sig_option_changed.emit('collvalue', state)
        self.model.collvalue = state
            
    def edit_item(self):
        """Edit item"""
        index = self.currentIndex()
        if not index.isValid():
            return
        self.edit(index)
    
    def remove_item(self):
        """Remove item"""
        indexes = self.selectedIndexes()
        if not indexes:
            return
        for index in indexes:
            if not index.isValid():
                return
        one = _("Do you want to remove selected item?")
        more = _("Do you want to remove all selected items?")
        answer = QMessageBox.question(self, _( "Remove"),
                                      one if len(indexes) == 1 else more,
                                      QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            idx_rows = unsorted_unique(map(lambda idx: idx.row(), indexes))
            keys = [ self.model.keys[idx_row] for idx_row in idx_rows ]
            self.remove_values(keys)

    def copy_item(self, erase_original=False):
        """Copy item"""
        indexes = self.selectedIndexes()
        if not indexes:
            return
        idx_rows = unsorted_unique(map(lambda idx: idx.row(), indexes))
        if len(idx_rows) > 1 or not indexes[0].isValid():
            return
        orig_key = self.model.keys[idx_rows[0]]
        new_key, valid = QInputDialog.getText(self, _( 'Rename'), _( 'Key:'),
                                              QLineEdit.Normal,orig_key)
        if valid and unicode(new_key):
            new_key = try_to_eval(unicode(new_key))
            if new_key == orig_key:
                return
            self.copy_value(orig_key, new_key)
            if erase_original:
                self.remove_values([orig_key])
    
    def duplicate_item(self):
        """Duplicate item"""
        self.copy_item()

    def rename_item(self):
        """Rename item"""
        self.copy_item(True)
    
    def insert_item(self):
        """Insert item"""
        index = self.currentIndex()
        if not index.isValid():
            row = self.model.rowCount()
        else:
            row = index.row()
        data = self.model.get_data()
        if isinstance(data, list):
            key = row
            data.insert(row, '')
        elif isinstance(data, dict):
            key, valid = QInputDialog.getText(self, _( 'Insert'), _( 'Key:'),
                                              QLineEdit.Normal)
            if valid and unicode(key):
                key = try_to_eval(unicode(key))
            else:
                return
        else:
            return
        value, valid = QInputDialog.getText(self, _('Insert'), _('Value:'),
                                            QLineEdit.Normal)
        if valid and unicode(value):
            self.new_value(key, try_to_eval(unicode(value)))
            
    def __prepare_plot(self):
        try:
            import guiqwt.pyplot #@UnusedImport
            return True
        except ImportError:
            try:
                if 'matplotlib' not in sys.modules:
                    from spyderlib import mpl_patch
                    mpl_patch.set_backend("Qt4Agg")
                    mpl_patch.apply()
                return True
            except ImportError:
                QMessageBox.warning(self, _("Import error"),
                                    _("Please install <b>matplotlib</b>"
                                      " or <b>guiqwt</b>."))

    def plot_item(self):
        """Plot item"""
        index = self.currentIndex()
        if self.__prepare_plot():
            key = self.model.get_key(index)
            try:
                self.plot(key)
            except ValueError, error:
                QMessageBox.critical(self, _( "Plot"),
                                     _("<b>Unable to plot data.</b>"
                                       "<br><br>Error message:<br>%s"
                                       ) % str(error))
            
    def imshow_item(self):
        """Imshow item"""
        index = self.currentIndex()
        if self.__prepare_plot():
            key = self.model.get_key(index)
            try:
                if self.is_image(key):
                    self.show_image(key)
                else:
                    self.imshow(key)
            except ValueError, error:
                QMessageBox.critical(self, _( "Plot"),
                                     _("<b>Unable to show image.</b>"
                                       "<br><br>Error message:<br>%s"
                                       ) % str(error))
            
    def save_array(self):
        """Save array"""
        title = _( "Save array")
        if self.array_filename is None:
            self.array_filename = os.getcwdu()
        self.emit(SIGNAL('redirect_stdio(bool)'), False)
        filename, _selfilter = getsavefilename(self, title,
                                               self.array_filename,
                                               _("NumPy arrays")+" (*.npy)")
        self.emit(SIGNAL('redirect_stdio(bool)'), True)
        if filename:
            self.array_filename = filename
            data = self.delegate.get_value( self.currentIndex() )
            try:
                import numpy as np
                np.save(self.array_filename, data)
            except Exception, error:
                QMessageBox.critical(self, title,
                                     _("<b>Unable to save array</b>"
                                       "<br><br>Error message:<br>%s"
                                       ) % str(error))
    def copy(self):
        """Copy text to clipboard"""
        clipboard = QApplication.clipboard()
        clipl = []
        for idx in self.selectedIndexes():
            if not idx.isValid():
                continue
            clipl.append(unicode(self.delegate.get_value(idx)))
        clipboard.setText(u'\n'.join(clipl))
    
    def import_from_string(self, text, title=None):
        """Import data from string"""
        data = self.model.get_data()
        editor = ImportWizard(self, text, title=title,
                              contents_title=_("Clipboard contents"),
                              varname=fix_reference_name("data",
                                                         blacklist=data.keys()))
        if editor.exec_():
            var_name, clip_data = editor.get_data()
            self.new_value(var_name, clip_data)
    
    def paste(self):
        """Import text/data/code from clipboard"""
        clipboard = QApplication.clipboard()
        cliptext = u""
        if clipboard.mimeData().hasText():
            cliptext = unicode(clipboard.text())
        if cliptext.strip():
            self.import_from_string(cliptext, title=_("Import from clipboard"))
        else:
            QMessageBox.warning(self, _( "Empty clipboard"),
                                _("Nothing to be imported from clipboard."))
        

class DictEditorTableView(BaseTableView):
    """DictEditor table view"""
    def __init__(self, parent, data, readonly=False, title="",
                 names=False, truncate=True, minmax=False,
                 inplace=False, collvalue=True):
        BaseTableView.__init__(self, parent)
        self.dictfilter = None
        self.readonly = readonly or isinstance(data, tuple)
        DictModelClass = ReadOnlyDictModel if self.readonly else DictModel
        self.model = DictModelClass(self, data, title, names=names,
                                    truncate=truncate, minmax=minmax,
                                    collvalue=collvalue)
        self.setModel(self.model)
        self.delegate = DictDelegate(self, inplace=inplace)
        self.setItemDelegate(self.delegate)

        self.setup_table()
        self.menu = self.setup_menu(truncate, minmax, inplace, collvalue)
    
    #------ Remote/local API ---------------------------------------------------
    def remove_values(self, keys):
        """Remove values from data"""
        data = self.model.get_data()
        for key in sorted(keys,reverse=True):
            data.pop(key)
            self.set_data(data)

    def copy_value(self, orig_key, new_key):
        """Copy value"""
        data = self.model.get_data()
        data[new_key] = data[orig_key]
        self.set_data(data)
    
    def new_value(self, key, value):
        """Create new value in data"""
        data = self.model.get_data()
        data[key] = value
        self.set_data(data)
        
    def is_list(self, key):
        """Return True if variable is a list or a tuple"""
        data = self.model.get_data()
        return isinstance(data[key], (tuple, list))
        
    def get_len(self, key):
        """Return sequence length"""
        data = self.model.get_data()
        return len(data[key])
        
    def is_array(self, key):
        """Return True if variable is a numpy array"""
        data = self.model.get_data()
        return isinstance(data[key], ndarray)
        
    def is_image(self, key):
        """Return True if variable is a PIL.Image image"""
        data = self.model.get_data()
        return isinstance(data[key], Image)
    
    def is_dict(self, key):
        """Return True if variable is a dictionary"""
        data = self.model.get_data()
        return isinstance(data[key], dict)
        
    def get_array_shape(self, key):
        """Return array's shape"""
        data = self.model.get_data()
        return data[key].shape
        
    def get_array_ndim(self, key):
        """Return array's ndim"""
        data = self.model.get_data()
        return data[key].ndim
    
    def oedit(self, key):
        """Edit item"""
        data = self.model.get_data()
        from spyderlib.widgets.objecteditor import oedit
        oedit(data[key])
    
    def plot(self, key):
        """Plot item"""
        data = self.model.get_data()
        import spyderlib.pyplot as plt
        plt.figure()
        plt.plot(data[key])
        plt.show()
    
    def imshow(self, key):
        """Show item's image"""
        data = self.model.get_data()
        import spyderlib.pyplot as plt
        plt.figure()
        plt.imshow(data[key])
        plt.show()
            
    def show_image(self, key):
        """Show image (item is a PIL image)"""
        data = self.model.get_data()
        data[key].show()
    #---------------------------------------------------------------------------
        
    def refresh_menu(self):
        """Refresh context menu"""
        data = self.model.get_data()
        index = self.currentIndex()
        condition = (not isinstance(data, tuple)) and index.isValid() \
                    and not self.readonly
        self.edit_action.setEnabled( condition )
        self.remove_action.setEnabled( condition )
        self.insert_action.setEnabled( not self.readonly )
        self.refresh_plot_entries(index)
        
    def set_filter(self, dictfilter=None):
        """Set table dict filter"""
        self.dictfilter = dictfilter


class DictEditorWidget(QWidget):
    """Dictionary Editor Dialog"""
    def __init__(self, parent, data, readonly=False, title="", remote=False):
        QWidget.__init__(self, parent)
        if remote:
            self.editor = RemoteDictEditorTableView(self, data, readonly)
        else:
            self.editor = DictEditorTableView(self, data, readonly, title)
        layout = QVBoxLayout()
        layout.addWidget(self.editor)
        self.setLayout(layout)
        
    def set_data(self, data):
        """Set DictEditor data"""
        self.editor.set_data(data)
        
    def get_title(self):
        """Get model title"""
        return self.editor.model.title


class DictEditor(QDialog):
    """Dictionary/List Editor Dialog"""
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        
        # Destroying the C++ object right after closing the dialog box,
        # otherwise it may be garbage-collected in another QThread
        # (e.g. the editor's analysis thread in Spyder), thus leading to
        # a segmentation fault on UNIX or an application crash on Windows
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        self.data_copy = None
        self.widget = None
        
    def setup(self, data, title='', readonly=False, width=500,
              icon='dictedit.png', remote=False, parent=None):
        if isinstance(data, dict):
            # dictionnary
            self.data_copy = data.copy()
        else:
            # list, tuple
            self.data_copy = data[:]
        self.widget = DictEditorWidget(self, self.data_copy, title=title,
                                       readonly=readonly, remote=remote)
        
        layout = QVBoxLayout()
        layout.addWidget(self.widget)
        self.setLayout(layout)
        
        # Buttons configuration
        buttons = QDialogButtonBox.Ok
        if not readonly:
            buttons = buttons | QDialogButtonBox.Cancel
        bbox = QDialogButtonBox(buttons)
        self.connect(bbox, SIGNAL("accepted()"), SLOT("accept()"))
        if not readonly:
            self.connect(bbox, SIGNAL("rejected()"), SLOT("reject()"))
        layout.addWidget(bbox)

        constant = 121
        row_height = 30
        error_margin = 20
        height = constant + row_height*min([20, len(data)]) + error_margin
        self.resize(width, height)
        
        self.setWindowTitle(self.widget.get_title())
        if isinstance(icon, (str, unicode)):
            icon = get_icon(icon)
        self.setWindowIcon(icon)
        # Make the dialog act as a window
        self.setWindowFlags(Qt.Window)
        
    def get_value(self):
        """Return modified copy of dictionary or list"""
        # It is import to avoid accessing Qt C++ object as it has probably
        # already been destroyed, due to the Qt.WA_DeleteOnClose attribute
        return self.data_copy


#----Remote versions of DictDelegate and DictEditorTableView
class RemoteDictDelegate(DictDelegate):
    """DictEditor Item Delegate"""
    def __init__(self, parent=None, inplace=False,
                 get_value_func=None, set_value_func=None):
        DictDelegate.__init__(self, parent, inplace=inplace)
        self.get_value_func = get_value_func
        self.set_value_func = set_value_func
        
    def get_value(self, index):
        if index.isValid():
            name = index.model().keys[index.row()]
            return self.get_value_func(name)
    
    def set_value(self, index, value):
        if index.isValid():
            name = index.model().keys[index.row()]
            self.set_value_func(name, value)
        
class RemoteDictEditorTableView(BaseTableView):
    """DictEditor table view"""
    def __init__(self, parent, data, truncate=True, minmax=False,
                 inplace=False, collvalue=True, remote_editing=False,
                 get_value_func=None, set_value_func=None,
                 new_value_func=None, remove_values_func=None,
                 copy_value_func=None, is_list_func=None, get_len_func=None,
                 is_array_func=None, is_image_func=None, is_dict_func=None,
                 get_array_shape_func=None, get_array_ndim_func=None,
                 oedit_func=None, plot_func=None, imshow_func=None,
                 show_image_func=None):
        BaseTableView.__init__(self, parent)
        
        self.remote_editing_enabled = None
        
        self.remove_values = remove_values_func
        self.copy_value = copy_value_func
        self.new_value = new_value_func
        
        self.is_list = is_list_func
        self.get_len = get_len_func
        self.is_array = is_array_func
        self.is_image = is_image_func
        self.is_dict = is_dict_func
        self.get_array_shape = get_array_shape_func
        self.get_array_ndim = get_array_ndim_func
        self.oedit = oedit_func
        self.plot = plot_func
        self.imshow = imshow_func
        self.show_image = show_image_func
        
        self.dictfilter = None
        self.model = None
        self.delegate = None
        self.readonly = False
        self.model = DictModel(self, data, names=True,
                               truncate=truncate, minmax=minmax,
                               collvalue=collvalue, remote=True)
        self.setModel(self.model)
        self.delegate = RemoteDictDelegate(self, inplace,
                                           get_value_func, set_value_func)
        self.setItemDelegate(self.delegate)
        
        self.setup_table()
        self.menu = self.setup_menu(truncate, minmax, inplace, collvalue,
                                    remote_editing)

    def setup_menu(self, truncate, minmax, inplace, collvalue, remote_editing):
        """Setup context menu"""
        menu = BaseTableView.setup_menu(self, truncate, minmax,
                                        inplace, collvalue)
        if menu is None:
            self.remote_editing_action.setChecked(remote_editing)
            return
        
        self.remote_editing_action = create_action(self,
                _( "Edit data in the remote process"),
                tip=_("Editors are opened in the remote process for NumPy "
                      "arrays, PIL images, lists, tuples and dictionaries.\n"
                      "This avoids transfering large amount of data between "
                      "the remote process and Spyder (through the socket)."),
                toggled=self.toggle_remote_editing)
        self.remote_editing_action.setChecked(remote_editing)
        self.toggle_remote_editing(remote_editing)
        add_actions(menu, (self.remote_editing_action,))
        return menu
            
    def toggle_remote_editing(self, state):
        """Toggle remote editing state"""
        self.sig_option_changed.emit('remote_editing', state)
        self.remote_editing_enabled = state
            
    def edit_item(self):
        """
        Reimplement BaseTableView's method to edit item
        
        Some supported data types are directly edited in the remote process,
        thus avoiding to transfer large amount of data through the socket from
        the remote process to Spyder
        """
        if self.remote_editing_enabled:
            index = self.currentIndex()
            if not index.isValid():
                return
            key = self.model.get_key(index)
            if (self.is_list(key) or self.is_dict(key) 
                or self.is_array(key) or self.is_image(key)):
                # If this is a remote dict editor, the following avoid 
                # transfering large amount of data through the socket
                self.oedit(key)
            else:
                BaseTableView.edit_item(self)
        else:
            BaseTableView.edit_item(self)


def get_test_data():
    """Create test data"""
    import numpy as np
    image = PIL.Image.fromarray(np.random.random_integers(255, size=(100, 100)))
    testdict = {'d': 1, 'a': np.random.rand(10, 10), 'b': [1, 2]}
    testdate = datetime.date(1945, 5, 8)
    return {'str': 'kjkj kj k j j kj k jkj',
            'unicode': u'éù',
            'list': [1, 3, [sorted, 5, 6], 'kjkj', None],
            'tuple': ([1, testdate, testdict], 'kjkj', None),
            'dict': testdict,
            'float': 1.2233,
            'int': 223,
            'bool': True,
            'array': np.random.rand(10, 10),
            '1D-array': np.linspace(-10, 10),
            'empty_array': np.array([]),
            'image': image,
            'date': testdate,
            'datetime': datetime.datetime(1945, 5, 8),
            'complex': 2+1j,
            'complex64': np.complex64(2+1j),
            'int8_scalar': np.int8(8),
            'int16_scalar': np.int16(16),
            'int32_scalar': np.int32(32),
            'bool_scalar': np.bool(8),
            'unsupported1': np.arccos,
            'unsupported2': np.cast,
            1: (1, 2, 3), -5: ("a", "b", "c"), 2.5: np.array((4.0, 6.0, 8.0)),            
            }

def test():
    """Dictionary editor test"""
    _app = qapplication() #analysis:ignore
    dialog = DictEditor()
    dialog.setup(get_test_data())
    if dialog.exec_():
        print "out:", dialog.get_value()
    
def remote_editor_test():
    """Remote dictionary editor test"""
    from spyderlib.plugins.variableexplorer import VariableExplorer
    from spyderlib.widgets.externalshell.monitor import make_remote_view
    remote = make_remote_view(get_test_data(), VariableExplorer.get_settings())
    from pprint import pprint
    pprint(remote)
    app = qapplication()
    dialog = DictEditor(remote, remote=True)
    dialog.show()
    app.exec_()
    if dialog.result():
        print dialog.get_value()

if __name__ == "__main__":
    test()