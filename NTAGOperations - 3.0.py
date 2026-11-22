# -*- coding: utf-8 -*-
import sys
import binascii
import sqlite3
import csv
import os
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                           QLabel, QPushButton, QTextEdit, QComboBox, QTabWidget,
                           QLineEdit, QCheckBox, QFileDialog, QMessageBox, 
                           QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
                           QSplitter, QTreeWidget, QTreeWidgetItem, QProgressBar)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QSettings
from PyQt5.QtGui import QColor, QFont
import nfc
from nfc.tag import tt2, tt3, tt4
import usb.core
import serial.tools.list_ports
from cryptography.fernet import Fernet
import hashlib

# 全局配置
CONFIG = {
    "AES_KEY": Fernet.generate_key(),
    "DB_FILE": "ntag_manager.db",
    "LOG_FILE": "operation_log.txt"
}

class NTAGOperations(QThread):
    """NTAG操作核心引擎"""
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)
    tag_detected = pyqtSignal(dict)
    operation_complete = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.current_operation = None
        self.operation_data = None
        self.running = False
        self.clf = None
        
    def set_operation(self, operation, **kwargs):
        """设置当前操作"""
        self.current_operation = operation
        self.operation_data = kwargs
        
    def run(self):
        """执行操作的主循环"""
        self.running = True
        try:
            self.clf = nfc.ContactlessFrontend('usb')
            if not self.clf:
                self.log_message.emit("❌ 未检测到读卡器设备")
                return
                
            while self.running:
                if self.current_operation == "detect":
                    self._detect_tag()
                elif self.current_operation == "read":
                    self._read_tag()
                elif self.current_operation == "write":
                    self._write_tag()
                elif self.current_operation == "format":
                    self._format_tag()
                elif self.current_operation == "batch":
                    self._batch_process()
                    
                self.msleep(500)
                
        except Exception as e:
            self.log_message.emit(f"❌ 硬件错误: {str(e)}")
        finally:
            if self.clf:
                self.clf.close()
                
    def _detect_tag(self):
        """检测标签类型"""
        tag = self.clf.connect(rdwr={'on-connect': lambda tag: False})
        if tag:
            info = self._parse_tag_info(tag)
            self.tag_detected.emit(info)
            
    def _read_tag(self):
        """读取标签数据"""
        tag = self.clf.connect(rdwr={'on-connect': lambda tag: False})
        if tag:
            info = self._parse_tag_info(tag)
            if isinstance(tag, tt2.Type2Tag):
                info['data'] = self._read_ntag(tag)
            self.operation_complete.emit(info)
            
    def _write_tag(self):
        """写入标签数据"""
        tag = self.clf.connect(rdwr={'on-connect': lambda tag: False})
        if tag and self.operation_data.get('data'):
            if isinstance(tag, tt2.Type2Tag):
                self._write_ntag(tag, self.operation_data['data'])
                self.log_message.emit("✅ 数据写入成功")
                
    def _format_tag(self):
        """格式化标签"""
        tag = self.clf.connect(rdwr={'on-connect': lambda tag: False})
        if tag:
            if isinstance(tag, tt2.Type2Tag):
                for block in range(4, 16):
                    try:
                        tag.write(block, bytearray([0]*4))
                    except:
                        pass
                self.log_message.emit("✅ 标签已格式化")
                
    def _batch_process(self):
        """批量处理标签"""
        tasks = self.operation_data.get('tasks', [])
        for i, task in enumerate(tasks):
            if not self.running:
                break
                
            self.progress.emit(int((i+1)/len(tasks)*100))
            # 实际批量操作逻辑需要根据具体需求实现
            
    def _parse_tag_info(self, tag):
        """解析标签信息"""
        info = {
            'uid': tag.identifier.hex(),
            'type': tag.type,
            'product': str(tag.product),
            'is_ndef': bool(tag.ndef)
        }
        
        # NTAG型号检测
        if isinstance(tag, tt2.Type2Tag):
            try:
                version = tag.read(0x12)[0]
                ntag_types = {
                    0x12: 'NTAG213',
                    0x3E: 'NTAG215', 
                    0x6D: 'NTAG216',
                    0x72: 'NTAG424'
                }
                info['ntag_type'] = ntag_types.get(version, 'Unknown NTAG')
            except:
                pass
                
        return info
        
    def _read_ntag(self, tag):
        """读取NTAG数据"""
        data = []
        for block in range(16):  # 读取前16个块
            try:
                data.append(binascii.hexlify(tag.read(block)).decode())
            except:
                data.append("00000000")
        return data
        
    def _write_ntag(self, tag, data):
        """写入NTAG数据"""
        if isinstance(data, str):
            data = [data[i:i+8] for i in range(0, len(data), 8)]
            
        for i, block in enumerate(data[:12]):  # 避免写入系统区域
            try:
                tag.write(4+i, bytearray.fromhex(block))
            except:
                self.log_message.emit(f"⚠️ 块 {4+i} 写入失败")

class NTAGManager(QMainWindow):
    """主界面"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("终极NTAG管理工具 v4.0")
        self.resize(1400, 900)
        
        # 初始化
        self.ntag_worker = NTAGOperations()
        self.current_tag = None
        self.settings = QSettings("NTAG", "UltimateTool")
        
        # 创建界面
        self.init_ui()
        self.init_db()
        self.init_connections()
        
    def init_ui(self):
        """初始化用户界面"""
        # 主布局
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # 顶部工具栏
        toolbar = self.create_toolbar()
        
        # 中心区域
        center_splitter = QSplitter(Qt.Horizontal)
        
        # 左侧设备面板
        left_panel = self.create_left_panel()
        
        # 右侧功能选项卡
        right_tabs = QTabWidget()
        self.setup_core_tab(right_tabs)
        self.setup_utils_tab(right_tabs)
        self.setup_hardware_tab(right_tabs)
        
        center_splitter.addWidget(left_panel)
        center_splitter.addWidget(right_tabs)
        center_splitter.setStretchFactor(1, 3)
        
        # 底部状态栏
        status_bar = self.create_statusbar()
        
        # 组装主布局
        main_layout.addWidget(toolbar)
        main_layout.addWidget(center_splitter)
        main_layout.addWidget(status_bar)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QWidget()
        layout = QHBoxLayout()
        
        btn_scan = QPushButton("扫描设备")
        btn_import = QPushButton("导入数据")
        btn_export = QPushButton("导出数据")
        btn_settings = QPushButton("设置")
        
        layout.addWidget(btn_scan)
        layout.addWidget(btn_import)
        layout.addWidget(btn_export)
        layout.addStretch()
        layout.addWidget(btn_settings)
        
        toolbar.setLayout(layout)
        return toolbar
        
    def create_left_panel(self):
        """创建左侧设备面板"""
        panel = QWidget()
        layout = QVBoxLayout()
        
        # 设备树
        self.device_tree = QTreeWidget()
        self.device_tree.setHeaderLabel("NFC设备")
        
        # 标签信息
        self.tag_info = QTextEdit()
        self.tag_info.setReadOnly(True)
        
        # 快速操作
        quick_actions = QGroupBox("快速操作")
        quick_layout = QVBoxLayout()
        btn_read = QPushButton("读取标签")
        btn_write = QPushButton("写入标签")
        btn_format = QPushButton("格式化")
        quick_layout.addWidget(btn_read)
        quick_layout.addWidget(btn_write)
        quick_layout.addWidget(btn_format)
        quick_actions.setLayout(quick_layout)
        
        layout.addWidget(self.device_tree)
        layout.addWidget(self.tag_info)
        layout.addWidget(quick_actions)
        
        panel.setLayout(layout)
        return panel
        
    def setup_core_tab(self, tabs):
        """设置核心功能选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # NDEF编辑器
        ndef_group = QGroupBox("NDEF记录编辑器")
        ndef_layout = QVBoxLayout()
        self.ndef_table = QTableWidget(0, 3)
        self.ndef_table.setHorizontalHeaderLabels(["类型", "内容", "操作"])
        ndef_layout.addWidget(self.ndef_table)
        ndef_group.setLayout(ndef_layout)
        
        # 数据编辑器
        data_editor = QGroupBox("数据编辑器")
        editor_layout = QVBoxLayout()
        self.data_edit = QTextEdit()
        self.data_edit.setPlaceholderText("输入十六进制数据...")
        editor_layout.addWidget(self.data_edit)
        data_editor.setLayout(editor_layout)
        
        layout.addWidget(ndef_group)
        layout.addWidget(data_editor)
        tab.setLayout(layout)
        tabs.addTab(tab, "核心功能")
        
    def setup_utils_tab(self, tabs):
        """设置实用工具选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # 批量操作
        batch_group = QGroupBox("批量操作")
        batch_layout = QVBoxLayout()
        self.batch_table = QTableWidget(0, 4)
        self.batch_table.setHorizontalHeaderLabels(["UID", "类型", "状态", "操作"])
        batch_layout.addWidget(self.batch_table)
        batch_group.setLayout(batch_layout)
        
        # 数据库查看
        db_group = QGroupBox("标签数据库")
        db_layout = QVBoxLayout()
        self.db_table = QTableWidget(0, 3)
        self.db_table.setHorizontalHeaderLabels(["UID", "类型", "最后访问"])
        db_layout.addWidget(self.db_table)
        db_group.setLayout(db_layout)
        
        layout.addWidget(batch_group)
        layout.addWidget(db_group)
        tab.setLayout(layout)
        tabs.addTab(tab, "实用工具")
        
    def setup_hardware_tab(self, tabs):
        """设置硬件选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # 多设备管理
        multi_dev = QGroupBox("多设备管理")
        multi_layout = QVBoxLayout()
        self.device_list = QComboBox()
        self.btn_refresh_dev = QPushButton("刷新设备")
        multi_layout.addWidget(self.device_list)
        multi_layout.addWidget(self.btn_refresh_dev)
        multi_dev.setLayout(multi_layout)
        
        # 手机联动
        phone_group = QGroupBox("手机NFC联动")
        phone_layout = QVBoxLayout()
        self.btn_connect_phone = QPushButton("连接手机")
        phone_layout.addWidget(self.btn_connect_phone)
        phone_group.setLayout(phone_layout)
        
        layout.addWidget(multi_dev)
        layout.addWidget(phone_group)
        tab.setLayout(layout)
        tabs.addTab(tab, "硬件扩展")
        
    def create_statusbar(self):
        """创建状态栏"""
        status = QWidget()
        layout = QHBoxLayout()
        
        self.status_label = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setVisible(False)
        
        layout.addWidget(self.status_label, 1)
        layout.addWidget(self.progress_bar)
        
        status.setLayout(layout)
        return status
        
    def init_db(self):
        """初始化数据库"""
        self.db_conn = sqlite3.connect(CONFIG["DB_FILE"])
        cursor = self.db_conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            uid TEXT PRIMARY KEY,
            type TEXT,
            data BLOB,
            last_accessed DATETIME
        )''')
        self.db_conn.commit()
        
    def init_connections(self):
        """初始化信号连接"""
        self.ntag_worker.log_message.connect(self.update_log)
        self.ntag_worker.tag_detected.connect(self.update_tag_info)
        self.ntag_worker.operation_complete.connect(self.handle_operation_complete)
        self.ntag_worker.progress.connect(self.update_progress)
        
    def update_log(self, message):
        """更新日志"""
        self.status_label.setText(message)
        with open(CONFIG["LOG_FILE"], "a") as f:
            f.write(f"[{datetime.now()}] {message}\n")
            
    def update_tag_info(self, info):
        """更新标签信息"""
        self.current_tag = info
        text = f"UID: {info['uid']}\n类型: {info.get('ntag_type', info['type'])}"
        if 'data' in info:
            text += f"\n数据长度: {len(info['data'])}字节"
        self.tag_info.setText(text)
        
    def handle_operation_complete(self, result):
        """处理操作完成"""
        if result.get('data'):
            self.display_data(result['data'])
            
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
        self.progress_bar.setVisible(value > 0 and value < 100)
        
    def display_data(self, data):
        """显示标签数据"""
        if isinstance(data, list):
            self.data_edit.setText("\n".join(data))
        else:
            self.data_edit.setText(data)
            
    def start_operation(self, operation, **kwargs):
        """开始NTAG操作"""
        if self.ntag_worker.isRunning():
            QMessageBox.warning(self, "警告", "当前有操作正在进行")
            return
            
        self.ntag_worker.set_operation(operation, **kwargs)
        self.ntag_worker.start()
        
    def closeEvent(self, event):
        """关闭事件处理"""
        self.ntag_worker.running = False
        if self.ntag_worker.isRunning():
            self.ntag_worker.wait(2000)
        self.db_conn.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置高DPI支持
    app.setAttribute(Qt.AA_EnableHighDpiScaling)
    
    # 检查依赖
    try:
        import nfc
        from cryptography.fernet import Fernet
    except ImportError as e:
        QMessageBox.critical(None, "缺少依赖", f"请安装: {str(e)}")
        sys.exit(1)
        
    # 创建并显示主窗口
    window = NTAGManager()
    window.show()
    
    sys.exit(app.exec_())