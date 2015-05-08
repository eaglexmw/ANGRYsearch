#!/usr/bin/python
# -*- coding: utf-8 -*-

import base64
from datetime import datetime
import locale
import os
from PySide.QtCore import *
from PySide.QtGui import *
import re
import scandir
import sqlite3
import subprocess
import sys


# print(os.__file__)
# QTHREAD FOR ASYNC SEARCHES IN THE DATABASE
# CALLED ON EVERY KEYPRESS
# RETURNS FIRST 500(numb_results) RESULTS MATCHING THE QUERY
class thread_db_query(QThread):
    db_query_signal = Signal(dict)

    def __init__(self, db_query, numb_results, parent=None):
        super(thread_db_query, self).__init__(parent)
        self.numb_results = numb_results
        self.db_query = db_query
        strip_and_split = db_query.strip('*').split('*')
        rx = '('+'|'.join(map(re.escape, strip_and_split))+')'
        self.regex_queries = re.compile(rx, re.IGNORECASE)

    def run(self):
        cur = con.cursor()
        cur.execute('''SELECT * FROM vt_locate_data_table WHERE file_path_col
                        MATCH ? LIMIT ?''',
                    (self.db_query, self.numb_results))
        tuppled_500 = cur.fetchall()

        bold_results_500 = []

        for tup in tuppled_500:
            bold = self.bold_text(tup[1])
            item = {'dir': tup[0], 'path': tup[1], 'bold_path': bold}
            bold_results_500.append(item)

        signal_message = {'input': self.db_query, 'results': bold_results_500}
        self.db_query_signal.emit(signal_message)

    def bold_text(self, line):
        return re.sub(self.regex_queries, '<b>\\1</b>', line)


# QTHREAD FOR UPDATING THE DATABASE
# PREVENTS LOCKING UP THE GUI AND ALLOWS TO SHOW STEPS PROGRESS
class thread_database_update(QThread):
    db_update_signal = Signal(str)

    def __init__(self, sudo_passwd, parent=None):
        self.db_path = '/var/lib/angrysearch/angry_database.db'
        self.temp_db_path = '/tmp/angry_database.db'
        super(thread_database_update, self).__init__(parent)
        self.sudo_passwd = sudo_passwd
        self.table = []

    def run(self):
        self.db_update_signal.emit('label_1')
        self.crawling_drives()

        self.db_update_signal.emit('label_2')
        self.new_database()

        self.db_update_signal.emit('label_3')
        self.replace_old_db_with_new()

        self.db_update_signal.emit('the_end_of_the_update')

    def crawling_drives(self):
        def error(err):
            print(err)

        root_dir = b'/'
        exclude = [b'.snapshots',
                   b'dev',
                   b'proc',
                   b'root',
                   b'home/ja/Documents/Linux']
        self.tstart = datetime.now()

        self.table = []
        dir_list = []
        file_list = []

        for root, dirs, files in scandir.walk(root_dir, onerror=error):

            dirs.sort()
            dirs[:] = [d for d in dirs if d not in exclude]

            for dname in dirs:
                dir_list.append(('1', os.path.join(root, dname).decode(
                    encoding='utf-8', errors='ignore')))
            for fname in files:
                file_list.append(('0', os.path.join(root, fname).decode(
                    encoding='utf-8', errors='ignore')))

        self.table = dir_list + file_list

        print(str(datetime.now() - self.tstart))

    def new_database(self):
        global con

        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

        con = sqlite3.connect(self.temp_db_path, check_same_thread=False)
        cur = con.cursor()
        cur.execute('''CREATE VIRTUAL TABLE vt_locate_data_table
                        USING fts4(directory, file_path_col)''')

        self.tstart = datetime.now()

        for x in self.table:
            cur.execute('''INSERT INTO vt_locate_data_table VALUES
                            (?, ?)''', (x[0], x[1]))

        con.commit()
        print(str(datetime.now() - self.tstart))

    def replace_old_db_with_new(self):
        global con

        if not os.path.exists(self.temp_db_path):
            return
        if not os.path.exists('/var/lib/angrysearch/'):
            cmd = ['sudo', 'mkdir', '/var/lib/angrysearch/']
            p = subprocess.Popen(cmd, stdout=PIPE, stderr=subprocess.PIPE,
                                 stdin=subprocess.PIPE)
            p.stdin.write(bytes(self.sudo_passwd+'\n', 'ASCII'))
            p.stdin.flush()
            p.wait()

        cmd = ['sudo', '-S', 'mv', '-f', self.temp_db_path, self.db_path]
        p = subprocess.Popen(cmd, stderr=subprocess.PIPE,
                             stdin=subprocess.PIPE)
        p.stdin.write(bytes(self.sudo_passwd+'\n', 'ASCII'))
        p.stdin.flush()
        p.wait()

        con = sqlite3.connect(self.db_path, check_same_thread=False)


# THE PRIMARY GUI, THE WIDGET WITHIN THE MAINWINDOW
class center_widget(QWidget):
    def __init__(self):
        super(center_widget, self).__init__()
        self.initUI()

    def initUI(self):
        self.search_input = QLineEdit()
        self.main_list = QListView()
        self.main_list.setItemDelegate(HTMLDelegate())
        self.upd_button = QPushButton('update')

        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(self.search_input, 1, 1)
        grid.addWidget(self.upd_button, 1, 4)
        grid.addWidget(self.main_list, 2, 1, 4, 4)
        self.setLayout(grid)

        self.setTabOrder(self.search_input, self.main_list)
        self.setTabOrder(self.main_list, self.upd_button)


# THE MAIN APPLICATION WINDOW WITH STATUS BAR AND LOGIC
class GUI_MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super(GUI_MainWindow, self).__init__(parent)
        self.settings = QSettings('angrysearch', 'angrysearch')
        self.set = {'file_manager': 'xdg-open',
                    'file_manager_receives_file_path': False,
                    'number_of_results': '500'}
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

    def closeEvent(self, event):
        self.settings.setValue('Last_Run/geometry', self.saveGeometry())
        self.settings.setValue('Last_Run/window_state', self.saveState())
        if not self.settings.value('file_manager'):
            self.settings.setValue('file_manager', 'xdg-open')
        if not self.settings.value('file_manager_receives_file_path'):
            self.settings.setValue('file_manager_receives_file_path', 'false')
        if not self.settings.value('number_of_results'):
            self.settings.setValue('number_of_results', '500')
        event.accept()

    def init_GUI(self):
        self.locale_current = locale.getdefaultlocale()
        self.icon = self.get_icon()
        self.setWindowIcon(self.icon)
        self.model = QStandardItemModel()

        self.threads = []
        self.file_list = []

        self.center = center_widget()
        self.setCentralWidget(self.center)

        self.setWindowTitle('ANGRYsearch')
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.center.main_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.center.main_list.clicked.connect(self.single_click)
        self.center.main_list.activated.connect(self.double_click_enter)

        self.center.search_input.textChanged[str].connect(self.on_input_change)
        self.center.upd_button.clicked.connect(self.clicked_button_updatedb)

        self.show()
        self.show_first_500()
        self.make_sys_tray()

    def make_sys_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            menu = QMenu()
            menu.addAction('v0.9.1')
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

    def on_input_change(self, input):
        if input == '':
            self.show_first_500()
            return
        search_terms = input.split(' ')
        t = '*'
        for x in search_terms:
            t += x + '*'
        self.new_query_new_thread(t)

    def new_query_new_thread(self, input):
        n = self.set['number_of_results']
        if len(self.threads) > 30:
            del self.threads[0:9]
        self.threads.append({'input': input,
                            'thread': thread_db_query(input, n)})
        self.threads[-1]['thread'].db_query_signal.connect(
            self.database_query_done, Qt.QueuedConnection)
        self.threads[-1]['thread'].start()

    # CHECK IF THE QUERY IS THE LAST ONE BEFORE SHOWING THE DATA
    def database_query_done(self, db_query_result):
        if (db_query_result['input'] != self.threads[-1]['input']):
            return
        self.update_file_list_results(db_query_result['results'])

    def update_file_list_results(self, data):
        self.model = QStandardItemModel()
        file_icon = self.style().standardIcon(QStyle.SP_FileIcon)
        dir_icon = self.style().standardIcon(QStyle.SP_DirIcon)

        for n in data:
            item = QStandardItem(n['bold_path'])
            item.path = n['path']
            if n['dir'] == '1':
                item.setIcon(dir_icon)
            else:
                item.setIcon(file_icon)
            self.model.appendRow(item)

        self.center.main_list.setModel(self.model)
        total = str(locale.format('%d', len(data), grouping=True))
        self.status_bar.showMessage(total)

    # RUNS ON START OR ON EMPTY INPUT
    def show_first_500(self):
        cur = con.cursor()
        cur.execute('''SELECT name FROM sqlite_master WHERE
                        type="table" AND name="vt_locate_data_table"''')
        if cur.fetchone() is None:
            self.status_bar.showMessage('0')
            self.tutorial()
            return

        cur.execute('''SELECT * FROM vt_locate_data_table
                        LIMIT ?''', (self.set['number_of_results'],))
        tuppled_500 = cur.fetchall()

        bold_results_500 = []

        for tup in tuppled_500:
            item = {'dir': tup[0], 'path': tup[1], 'bold_path': tup[1]}
            bold_results_500.append(item)

        self.update_file_list_results(bold_results_500)
        cur.execute('''SELECT COALESCE(MAX(rowid), 0)
                        FROM vt_locate_data_table''')
        total_rows_numb = cur.fetchone()[0]
        total = str(locale.format('%d', total_rows_numb, grouping=True))
        self.status_bar.showMessage(str(total))

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
            self.status_bar.showMessage(str('NO PERMISSION'))
        else:
            self.status_bar.showMessage(str('NOPE'))

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

    def tutorial(self):
        chat = ['  ANGRYsearch',
                '   • uses "locate" command to create own database',
                '   • locate uses "updatedb" to update its own database',
                '   • configuration can be find in /etc/updatedb.conf',
                '   • there you can exclude paths from being searched',
                '   • Btrfs users really want to exclude snapshots',
                '',
                '   • learn more about locate on it\'s manpage',
                '   • learn more about updatedb on it\'s manpage',
                '',
                '   • ANGRYsearch database is in /var/lib/angrysearch/',
                '   • with ~1 mil files indexed it\'s size is roughly 200MB',
                '   • config file is in ~/.config/angrysearch/',
                '   • currently you can set file manager manually there',
                '   • otherwise xdg-open is used which might have few hickups',
                '',
                '  time to press the updatedb button in the top right corner'
                ]
        self.center.main_list.setModel(QStringListModel(chat))

    def clicked_button_updatedb(self):
        self.sud = sudo_dialog(self)
        self.sud.exec_()
        self.show_first_500()

    def string_to_boolean(self, str):
        if str in ['true', 'True', 'yes', 'y', '1']:
            return True
        else:
            return False


# UPDATE DATABASE DIALOG WITH PROGRESS SHOWN
class sudo_dialog(QDialog):
    def __init__(self, parent):
        self.values = dict()
        self.last_signal = ''
        super(sudo_dialog, self).__init__(parent)
        self.initUI()

    def __setitem__(self, k, v):
        self.values[k] = v

    def __getitem__(self, k):
        return None if k not in self.values else self.values[k]

    def initUI(self):
        self.setWindowTitle('Database Update')
        self.label_0 = QLabel('sudo password:')
        self.passwd_input = QLineEdit()
        self.passwd_input.setEchoMode(QLineEdit.Password)
        self.label_1 = QLabel('• crawling the file system')
        self.label_2 = QLabel('• creating a new database')
        self.label_3 = QLabel('• replacing old database\n  '
                              'with the new one')
        self.OK_button = QPushButton('OK')
        self.OK_button.setEnabled(False)
        self.cancel_button = QPushButton('Cancel')

        self.label_1.setIndent(19)
        self.label_2.setIndent(19)
        self.label_3.setIndent(19)

        # TO MAKE SQUARE BRACKETS NOTATION WORK LATER ON
        # ALSO THE REASON FOR CUSTOM __getitem__ & __setitem__
        self['label_1'] = self.label_1
        self['label_2'] = self.label_2
        self['label_3'] = self.label_3

        grid = QGridLayout()
        grid.setSpacing(7)
        grid.addWidget(self.label_0, 0, 0)
        grid.addWidget(self.passwd_input, 0, 1)
        grid.addWidget(self.label_1, 1, 0, 1, 2)
        grid.addWidget(self.label_2, 2, 0, 1, 2)
        grid.addWidget(self.label_3, 3, 0, 1, 2)
        grid.addWidget(self.OK_button, 4, 0)
        grid.addWidget(self.cancel_button, 4, 1)
        self.setLayout(grid)

        self.OK_button.clicked.connect(self.clicked_OK_update_db)
        self.cancel_button.clicked.connect(self.clicked_cancel)
        self.passwd_input.textChanged[str].connect(self.password_typed)

    def password_typed(self, input):
        if len(input) > 0:
            self.OK_button.setEnabled(True)

    def clicked_cancel(self):
        self.accept()

    def clicked_OK_update_db(self):
        sudo_passwd = self.passwd_input.text()
        self.thread_updating = thread_database_update(sudo_passwd)
        self.thread_updating.db_update_signal.connect(
            self.sudo_dialog_receive_signal, Qt.QueuedConnection)
        self.thread_updating.start()

    def sudo_dialog_receive_signal(self, message):
        if message == 'the_end_of_the_update':
            self.accept()
            return

        label = self[message]
        label_alt = '➔' + label.text()[1:]
        label.setText(label_alt)

        if self.last_signal:
            prev_label = self[self.last_signal]
            prev_label_alt = '✔' + prev_label.text()[1:]
            prev_label.setText(prev_label_alt)

        self.last_signal = message


# CUSTOM DELEGATE TO GET HTML RICH TEXT IN LISTVIEW
class HTMLDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super(HTMLDelegate, self).__init__(parent)
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

        textRect = style.subElementRect(QStyle.SE_ItemViewItemText, options)
        painter.translate(textRect.topLeft())
        self.doc.documentLayout().draw(painter, ctx)

        painter.restore()

    def sizeHint(self, option, index):
        options = QStyleOptionViewItemV4(option)
        self.initStyleOption(options,index)
        return QSize(self.doc.idealWidth(), self.doc.size().height())


def open_database():
    path = '/var/lib/angrysearch/angry_database.db'
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
        ui = GUI_MainWindow()
        sys.exit(app.exec_())
