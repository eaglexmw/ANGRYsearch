#!/usr/bin/python
# -*- coding: utf-8 -*-

import base64
from datetime import datetime
import locale
import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import re
import sqlite3
import subprocess
import sys

try:
    import scandir
    SCANDIR_AVAILABLE = True
except ImportError:
    SCANDIR_AVAILABLE = False


# THREAD FOR ASYNC SEARCHES IN THE DATABASE, CALLED ON EVERY KEYPRESS
# RETURNS FIRST 500(number_of_results) RESULTS MATCHING THE QUERY
# fts4 VALUE DECIDES IF USE FAST INDEXED "MATCH" OR SUBSTRING "LIKE"
class Thread_db_query(QThread):
    db_query_signal = pyqtSignal(dict)

    def __init__(self, db_query, settings, parent=None):
        super().__init__()
        self.number_of_results = settings['number_of_results']
        self.fts4 = settings['fts4']
        self.db_query = db_query
        self.sql_query = self.query_adjustment_for_sqlite(db_query)

    def run(self):
        cur = con.cursor()
        if self.fts4 == 'false':
            cur.execute(
                '''SELECT * FROM angry_table WHERE path LIKE ? LIMIT ?''',
                (self.sql_query, self.number_of_results))
        else:
            cur.execute(
                '''SELECT * FROM angry_table WHERE path MATCH ? LIMIT ?''',
                (self.sql_query, self.number_of_results))
        tuppled_500 = cur.fetchall()
        signal_message = {'input': self.db_query, 'results': tuppled_500}
        self.db_query_signal.emit(signal_message)

    def query_adjustment_for_sqlite(self, input):
        if self.fts4 == 'false':
            joined = '%'.join(input.split())
            return '%{0}%'.format(joined)
        else:
            joined = '*'.join(input.split())
            return '*{0}*'.format(joined)


# THREAD FOR UPDATING THE DATABASE
# PREVENTS LOCKING UP THE GUI AND ALLOWS TO SHOW PROGRESS
class Thread_database_update(QThread):
    db_update_signal = pyqtSignal(str, str)
    crawl_signal = pyqtSignal(str)

    def __init__(self, settings, parent=None):
        super().__init__()
        self.settings = settings
        self.table = []
        self.tstart = None
        self.crawl_time = None
        self.database_time = None

    def run(self):
        self.db_update_signal.emit('label_1', None)
        self.crawling_drives()

        self.db_update_signal.emit('label_2', self.crawl_time)
        self.new_database()

        self.db_update_signal.emit('label_3', self.database_time)
        self.replace_old_db_with_new()

        self.db_update_signal.emit('the_end_of_the_update', None)

    def crawling_drives(self):
        def error(err):
            print(err)

        global SCANDIR_AVAILABLE

        exclude = []
        if self.settings.value('directories_excluded'):
            q = self.settings.value('directories_excluded').strip().split()
            exclude = [x.encode() for x in q]

        exclude.append(b'proc')

        root_dir = b'/'
        self.tstart = datetime.now()

        self.table = []
        dir_list = []
        file_list = []

        if SCANDIR_AVAILABLE:
            ror = scandir
        else:
            ror = os

        for root, dirs, files in ror.walk(root_dir, onerror=error):
            dirs.sort()
            files.sort()
            dirs[:] = [d for d in dirs if d not in exclude]
            self.crawl_signal.emit(root.decode(encoding='UTF-8',
                                               errors='ignore'))

            for dname in dirs:
                dir_list.append(('1', os.path.join(root, dname).decode(
                    encoding='UTF-8', errors='ignore')))
            for fname in files:
                file_list.append(('0', os.path.join(root, fname).decode(
                    encoding='UTF-8', errors='ignore')))

        self.table = dir_list + file_list

        self.crawl_time = datetime.now() - self.tstart
        self.crawl_time = self.time_difference(self.crawl_time.seconds)

    def new_database(self):
        global con
        temp_db_path = '/tmp/angry_database.db'

        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

        con = sqlite3.connect(temp_db_path, check_same_thread=False)
        cur = con.cursor()
        cur.execute('''CREATE VIRTUAL TABLE angry_table
                        USING fts4(directory, path)''')

        self.tstart = datetime.now()

        for x in self.table:
            cur.execute('''INSERT INTO angry_table VALUES (?, ?)''',
                        (x[0], x[1]))

        con.commit()
        self.database_time = datetime.now() - self.tstart
        self.database_time = self.time_difference(self.database_time.seconds)

    def replace_old_db_with_new(self):
        global con

        home = os.path.expanduser('~')
        db_path = home + '/.cache/angrysearch/angry_database.db'
        temp_db_path = '/tmp/angry_database.db'

        dir_path = os.path.dirname(db_path)

        if not os.path.exists(temp_db_path):
            return
        if not os.path.exists(dir_path):
            cmd = ['install', '-d', dir_path]
            p = subprocess.Popen(cmd)
            p.wait()

        cmd = ['mv', '-f', temp_db_path, db_path]
        p = subprocess.Popen(cmd,
                             stderr=subprocess.PIPE)
        p.wait()

        con = sqlite3.connect(db_path, check_same_thread=False)

    def time_difference(self, nseconds):
        mins, secs = divmod(nseconds, 60)
        return '{:0>2d}:{:0>2d}'.format(mins, secs)


# THE PRIMARY GUI, THE WIDGET WITHIN THE MAINWINDOW
class Center_widget(QWidget):
    def __init__(self):
        super(Center_widget, self).__init__()
        self.initUI()

    def initUI(self):
        self.search_input = QLineEdit()
        self.fts4_checkbox = QCheckBox()
        self.main_list = QListView()
        self.upd_button = QPushButton('update')

        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(self.search_input, 1, 1)
        grid.addWidget(self.fts4_checkbox, 1, 3)
        grid.addWidget(self.upd_button, 1, 4)
        grid.addWidget(self.main_list, 2, 1, 4, 4)
        self.setLayout(grid)

        self.setTabOrder(self.search_input, self.main_list)
        self.setTabOrder(self.main_list, self.upd_button)


# THE MAIN APPLICATION WINDOW WITH THE STATUS BAR AND LOGIC
class Gui_MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.settings = QSettings('angrysearch', 'angrysearch')
        self.set = {'fts4': 'true',
                    'file_manager': 'xdg-open',
                    'file_manager_receives_file_path': False,
                    'number_of_results': '500',
                    'directories_excluded': []}
        self.read_settings()
        self.init_GUI()

    def read_settings(self):
        if self.settings.value('Last_Run/geometry'):
            self.restoreGeometry(self.settings.value('Last_Run/geometry'))
        else:
            self.resize(640, 480)
            qr = self.frameGeometry()
            cp = QDesktopWidget().availableGeometry().center()
            qr.moveCenter(cp)
            self.move(qr.topLeft())

        if self.settings.value('Last_Run/window_state'):
            self.restoreState(self.settings.value('Last_Run/window_state'))

        if self.settings.value('fast_search_but_no_substring'):
            fts4 = self.settings.value('fast_search_but_no_substring')
            if fts4.lower() in ['false', 'no', '0', 'n', 'none', 'nope']:
                self.set['fts4'] = 'false'

        if self.settings.value('file_manager'):
            if self.settings.value('file_manager') not in ['', 'xdg-open']:
                self.set['file_manager'] = self.settings.value('file_manager')

                if self.settings.value('file_manager_receives_file_path'):
                    self.set['file_manager_receives_file_path'] = \
                        self.string_to_boolean(self.settings.value(
                            'file_manager_receives_file_path'))
            else:
                self.detect_file_manager()
        else:
            self.detect_file_manager()

        if self.settings.value('number_of_results'):
            if ((self.settings.value('number_of_results')).isdigit()):
                self.set['number_of_results'] = \
                    self.settings.value('number_of_results')

        if self.settings.value('directories_excluded'):
            self.set['directories_excluded'] = \
                self.settings.value('directories_excluded').strip().split()

    def closeEvent(self, event):
        if not self.settings.value('fast_search_but_no_substring'):
            self.settings.setValue('fast_search_but_no_substring', 'true')
        if not self.settings.value('file_manager'):
            self.settings.setValue('file_manager', 'xdg-open')
        if not self.settings.value('file_manager_receives_file_path'):
            self.settings.setValue('file_manager_receives_file_path', 'false')
        if not self.settings.value('number_of_results'):
            self.settings.setValue('number_of_results', '500')
        if not self.settings.value('directories_excluded'):
            self.settings.setValue('directories_excluded', '')
        self.settings.setValue('Last_Run/geometry', self.saveGeometry())
        self.settings.setValue('Last_Run/window_state', self.saveState())
        event.accept()

    def init_GUI(self):
        self.locale_current = locale.getdefaultlocale()
        self.icon = self.get_icon()
        self.setWindowIcon(self.icon)
        self.dir_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self.file_icon = self.style().standardIcon(QStyle.SP_FileIcon)

        self.model = QStandardItemModel()

        self.threads = []
        self.file_list = []

        self.center = Center_widget()
        self.setCentralWidget(self.center)

        self.setWindowTitle('ANGRYsearch')
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.center.fts4_checkbox.setToolTip(
            'check = fts4 indexing, fast\n'
            'uncheck = substrings work, slower')

        if self.set['fts4'] == 'true':
            self.center.fts4_checkbox.setChecked(True)
        self.center.fts4_checkbox.stateChanged.connect(self.checkbox_fts_click)

        self.center.main_list.setItemDelegate(self.HTMLDelegate())

        self.center.main_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.center.main_list.clicked.connect(self.single_click)
        self.center.main_list.activated.connect(self.double_click_enter)

        self.center.search_input.textChanged[str].connect(
            self.new_query_new_thread)
        self.center.upd_button.clicked.connect(self.clicked_button_updatedb)

        self.show()
        self.show_first_500()
        self.make_sys_tray()

        self.center.search_input.setFocus()

    def make_sys_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            menu = QMenu()
            menu.addAction('v0.9.3')
            menu.addSeparator()
            exitAction = menu.addAction('Quit')
            exitAction.triggered.connect(sys.exit)

            self.tray_icon = QSystemTrayIcon()
            self.tray_icon.setIcon(self.icon)
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.show()
            self.tray_icon.setToolTip('ANGRYsearch')
            self.tray_icon.activated.connect(self.sys_tray_clicking)

    def sys_tray_clicking(self, reason):
        if (reason == QSystemTrayIcon.DoubleClick or
                reason == QSystemTrayIcon.Trigger):
            self.show()
        elif (reason == QSystemTrayIcon.MiddleClick):
            QCoreApplication.instance().quit()

    def get_icon(self):
        base64_data = '''iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAABHN
                         CSVQICAgIfAhkiAAAAQNJREFUOI3t1M9KAlEcxfHPmP0xU6Ogo
                         G0teoCiHjAIfIOIepvKRUE9R0G0KNApfy0c8hqKKUMrD9zVGc4
                         9nPtlsgp5n6qSVSk7cBG8CJ6sEX63UEcXz4jE20YNPbygPy25Q
                         o6oE+fEPXFF7A5yA9Eg2sQDcU3sJd6k89O4iiMcYKVol3rH2Mc
                         a1meZ4hMdNPCIj+SjHHfFZU94/0Nwlv4rWoY7vhrdeLNoO86bG
                         lym/ge3lsHDdI2fojbBG6sUtzOiQ1wQOwk6GwWKHeJyHtxOcFi
                         0TpFaxmnhNcyIW45bQ6RS3Hq4MeB7Ltyahki9Gd2xidWiwG9va
                         nCZqi7xlZGVHfwN6+5nU/ccBUYAAAAASUVORK5CYII='''

        pm = QPixmap()
        pm.loadFromData(base64.b64decode(base64_data))
        i = QIcon()
        i.addPixmap(pm)
        return i

    # CALLED ON EVERY TEXT CHANGE IN THE SEARCH INPUT
    # QUERY THE DATABASE, LIST OF QUERIES TO KNOW THE LAST ONE
    def new_query_new_thread(self, input):
        if input == '':
            self.show_first_500()
            return

        if len(self.threads) > 30:
            del self.threads[0:20]

        self.threads.append({'input': input,
                            'thread': Thread_db_query(
                                input, self.set)})

        self.threads[-1]['thread'].db_query_signal.connect(
            self.database_query_done, Qt.QueuedConnection)
        self.threads[-1]['thread'].start()

    # CHECK IF THE QUERY IS THE LAST ONE BEFORE SHOWING THE DATA
    def database_query_done(self, db_query_result):
        if (db_query_result['input'] != self.threads[-1]['input']):
            return
        self.process_database_resuls(db_query_result)

    # FORMAT DATA FOR THE MODEL
    def process_database_resuls(self, data):
        self.model = QStandardItemModel()
        typed_text = data['input']
        results = data['results']

        strip_and_split = typed_text.strip().split()
        rx = '('+'|'.join(map(re.escape, strip_and_split))+')'
        self.regex_queries = re.compile(rx, re.IGNORECASE)

        for tup in results:
            path = tup[1]
            if typed_text:
                path = self.bold_text(tup[1])
            item = QStandardItem(path)
            item.path = tup[1]
            if tup[0] == '1':
                item.setIcon(self.dir_icon)
            else:
                item.setIcon(self.file_icon)
            self.model.appendRow(item)

        self.center.main_list.setModel(self.model)
        total = str(locale.format('%d', len(results), grouping=True))
        self.status_bar.showMessage(total)

    def bold_text(self, line):
        return re.sub(self.regex_queries, '<b>\\1</b>', line)

    # RUNS ON START OR ON EMPTY INPUT
    def show_first_500(self):
        cur = con.cursor()
        cur.execute('''SELECT name FROM sqlite_master WHERE
                        type="table" AND name="angry_table"''')
        if cur.fetchone() is None:
            self.status_bar.showMessage('0')
            self.tutorial()
            return

        cur.execute('''SELECT * FROM angry_table LIMIT ?''',
                    (self.set['number_of_results'],))
        tuppled_500 = cur.fetchall()

        self.process_database_resuls({'input': '', 'results': tuppled_500})

        cur.execute('''SELECT COALESCE(MAX(rowid), 0) FROM angry_table''')
        total_rows_numb = cur.fetchone()[0]
        total = locale.format('%d', total_rows_numb, grouping=True)
        self.status_bar.showMessage(total)

    def detect_file_manager(self):
        try:
            fm = subprocess.check_output(['xdg-mime', 'query',
                                          'default', 'inode/directory'])
            detected_fm = fm.decode('utf-8').strip().lower()

            known_fm = ['dolphin', 'nemo', 'nautilus', 'doublecmd']
            if any(item in detected_fm for item in known_fm):
                self.set['file_manager'] = detected_fm
                print('autodetected file manager: ' + detected_fm)
            else:
                self.set['file_manager'] = 'xdg-open'
        except Exception as err:
            self.set['file_manager'] = 'xdg-open'
            print(err)

    def single_click(self, QModelIndex):
        path = self.model.itemFromIndex(QModelIndex).path

        if not os.path.exists(path):
            self.status_bar.showMessage('NOT FOUND')
            return

        mime = subprocess.Popen(['xdg-mime', 'query', 'filetype', path],
                                stdout=subprocess.PIPE)
        mime.wait()
        if mime.returncode == 0:
            mime_type = mime.communicate()[0].decode('latin-1').strip()
            self.status_bar.showMessage(str(mime_type))
        elif mime.returncode == 5:
            self.status_bar.showMessage('NO PERMISSION')
        else:
            self.status_bar.showMessage('NOPE')

    def double_click_enter(self, QModelIndex):
        path = self.model.itemFromIndex(QModelIndex).path

        if not os.path.exists(path):
            self.status_bar.showMessage('NOT FOUND')
            return

        fm = self.set['file_manager']

        if os.path.isdir(path):
            known_fm = ['dolphin', 'nemo', 'nautilus', 'doublecmd']
            for x in known_fm:
                if x in fm:
                    subprocess.Popen([x, path])
                    return
            subprocess.Popen([fm, path])
        else:
            if 'dolphin' in fm:
                cmd = ['dolphin', '--select', path]
            elif 'nemo' in fm:
                cmd = ['nemo', path]
            elif 'nautilus' in fm:
                cmd = ['nautilus', path]
            elif 'doublecmd' in fm:
                cmd = ['doublecmd', path]
            else:
                if self.set['file_manager_receives_file_path']:
                    cmd = [fm, path]
                else:
                    parent_dir = os.path.abspath(os.path.join(path, os.pardir))
                    cmd = [fm, parent_dir]
            subprocess.Popen(cmd)

    def checkbox_fts_click(self, state):
        if state == Qt.Checked:
            self.set['fts4'] = 'true'
            self.settings.setValue('fast_search_but_no_substring', 'true')
        else:
            self.set['fts4'] = 'false'
            self.settings.setValue('fast_search_but_no_substring', 'false')
        current_search = self.center.search_input.text()
        self.new_query_new_thread(current_search)
        self.center.search_input.setFocus()

    def tutorial(self):
        chat = [
            '   • the database is in ~/.cache/angrysearch/angry_database.db',
            '   • ~1 mil files can take ~200MB and ~1m30s to index',
            '',
            '   • double-click opens the location in file manager',
            '',
            '   • checkbox in the right top corner changes search behavior',
            '   • by default checked, it provides very fast searching',
            '   • drawback is that it can\'t do word bound substrings',
            '   • it would not find "Pi<b>rate</b>s", or Whip<b>lash</b>"',
            '   • it would find "<b>Pir</b>ates", or "The-<b>Fif</b>th"',
            '   • unchecking it provides substring searches, but slower',
            '',
            '   • config file is in ~/.config/angrysearch/angrysearch.conf',
            ]

        self.center.main_list.setModel(QStringListModel(chat))
        self.status_bar.showMessage(
            'READ, then press the update button in the top right corner')

    def clicked_button_updatedb(self):
        self.u = Update_dialog_window(self)
        self.u.window_close_signal.connect(
            self.update_window_close, Qt.QueuedConnection)
        self.u.exec_()
        self.center.search_input.setFocus()

    def update_window_close(self, text):
        if text == 'update_win_ok':
            self.center.search_input.setText('')
            self.show_first_500()

    def string_to_boolean(self, str):
        if str in ['true', 'True', 'yes', 'y', '1']:
            return True
        else:
            return False

    # CUSTOM DELEGATE TO GET HTML RICH TEXT IN LISTVIEW
    class HTMLDelegate(QStyledItemDelegate):
        def __init__(self, parent=None):
            super().__init__()
            self.doc = QTextDocument(self)

        def paint(self, painter, option, index):
            painter.save()

            options = QStyleOptionViewItemV4(option)

            self.initStyleOption(options, index)
            self.doc.setHtml(options.text)
            options.text = ""

            style = QApplication.style() if options.widget is None \
                else options.widget.style()
            style.drawControl(QStyle.CE_ItemViewItem, options, painter)

            ctx = QAbstractTextDocumentLayout.PaintContext()

            if option.state & QStyle.State_Selected:
                ctx.palette.setColor(QPalette.Text, option.palette.color(
                    QPalette.Active, QPalette.HighlightedText))

            textRect = style.subElementRect(
                QStyle.SE_ItemViewItemText, options)

            thefuckyourshitup_constant = 4
            margin = (option.rect.height() - options.fontMetrics.height()) // 2
            margin = margin - thefuckyourshitup_constant
            textRect.setTop(textRect.top()+margin)

            painter.translate(textRect.topLeft())
            self.doc.documentLayout().draw(painter, ctx)

            painter.restore()

        def sizeHint(self, option, index):
            return QSize(self.doc.idealWidth(), self.doc.size().height())


# UPDATE DATABASE DIALOG WITH PROGRESS SHOWN
class Update_dialog_window(QDialog):
    window_close_signal = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.values = dict()
        self.last_signal = ''
        self.settings = QSettings('angrysearch', 'angrysearch')
        self.initUI()

    def __setitem__(self, k, v):
        self.values[k] = v

    def __getitem__(self, k):
        return None if k not in self.values else self.values[k]

    def initUI(self):
        self.excluded_dirs = ''
        if self.settings.value('directories_excluded'):
            self.excluded_dirs = \
                self.settings.value('directories_excluded').strip()

        self.setWindowTitle('Database Update')
        self.excluded_label = QLabel('ignored directories:')
        self.excluded_dirs_btn = QPushButton(self.excluded_dirs)
        self.crawl0_label = QLabel('progress:')
        self.crawl_label = QLabel('')
        self.label_1 = QLabel('• crawling the file system')
        self.label_2 = QLabel('• creating new database')
        self.label_3 = QLabel('• replacing old database')
        self.OK_button = QPushButton('OK')
        self.cancel_button = QPushButton('Cancel')

        if self.excluded_dirs == '':
            self.excluded_dirs_btn.setText('none')
            self.excluded_dirs_btn.setStyleSheet("color:#7700AA;font: italic;")

        self.label_1.setIndent(70)
        self.label_2.setIndent(70)
        self.label_3.setIndent(70)

        self.crawl_label.setMinimumWidth(170)

        self.excluded_dirs_btn.clicked.connect(self.exclude_dialog)

        # TO MAKE SQUARE BRACKETS NOTATION WORK LATER ON
        # ALSO THE REASON FOR CUSTOM __getitem__ & __setitem__
        self['label_1'] = self.label_1
        self['label_2'] = self.label_2
        self['label_3'] = self.label_3

        grid = QGridLayout()
        grid.setSpacing(7)
        grid.addWidget(self.excluded_label, 0, 0)
        grid.addWidget(self.excluded_dirs_btn, 0, 1)
        grid.addWidget(self.crawl0_label, 1, 0)
        grid.addWidget(self.crawl_label, 1, 1)
        grid.addWidget(self.label_1, 2, 0, 1, 2)
        grid.addWidget(self.label_2, 3, 0, 1, 2)
        grid.addWidget(self.label_3, 4, 0, 1, 2)
        grid.addWidget(self.OK_button, 5, 0)
        grid.addWidget(self.cancel_button, 5, 1)
        self.setLayout(grid)

        self.OK_button.clicked.connect(self.clicked_OK_update_db)
        self.cancel_button.clicked.connect(self.clicked_cancel)

        self.OK_button.setFocus()

    def exclude_dialog(self):
        text, ok = QInputDialog.getText(self, '~/.config/angrysearch/',
                                        'Directories to be ignored:',
                                        QLineEdit.Normal, self.excluded_dirs)
        if ok:
            text = text.strip()
            self.settings.setValue('directories_excluded', text)
            self.excluded_dirs = text
            if text == '':
                self.excluded_dirs_btn.setText('none')
                self.excluded_dirs_btn.setStyleSheet('color:#7700AA;'
                                                     'font:italic;')
            else:
                self.excluded_dirs_btn.setText(text)
                self.excluded_dirs_btn.setStyleSheet("color:#000;")
            self.OK_button.setFocus()

    def clicked_cancel(self):
        self.window_close_signal.emit('update_win_cancel')
        self.accept()

    def clicked_OK_update_db(self):
        self.thread_updating = Thread_database_update(self.settings)
        self.thread_updating.db_update_signal.connect(
            self.upd_dialog_receives_signal, Qt.QueuedConnection)
        self.thread_updating.crawl_signal.connect(
            self.upd_dialog_receives_crawl, Qt.QueuedConnection)

        self.thread_updating.start()

    def upd_dialog_receives_signal(self, message, time=''):
        if message == 'the_end_of_the_update':
            self.window_close_signal.emit('update_win_ok')
            self.accept()
            return

        label = self[message]
        label_alt = '➔{}'.format(label.text()[1:])
        label.setText(label_alt)

        if self.last_signal:
            prev_label = self[self.last_signal]
            prev_label_alt = '✔{} - {}'.format(prev_label.text()[1:], time)
            prev_label.setText(prev_label_alt)

        self.last_signal = message

    def upd_dialog_receives_crawl(self, message):
        self.crawl_label.setText(message)


def open_database():
    home = os.path.expanduser('~')
    path = home + '/.cache/angrysearch/angry_database.db'
    temp = '/tmp/angry_database.db'
    if os.path.exists(path):
        return sqlite3.connect(path, check_same_thread=False)
    else:
        if os.path.exists(temp):
            os.remove(temp)
        return sqlite3.connect(temp, check_same_thread=False)


if __name__ == '__main__':
    con = open_database()
    with con:
        app = QApplication(sys.argv)
        ui = Gui_MainWindow()
        sys.exit(app.exec_())
