import sys
import binascii
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, 
                           QLabel, QPushButton, QTextEdit, QComboBox,
                           QGroupBox, QTabWidget, QLineEdit, QCheckBox,
                           QFileDialog, QMessageBox, QSpinBox)

from PyQt5.QtCore import QThread, pyqtSignal, Qt
import nfc
from nfc.tag import tt2

class NTAGOperations(QThread):
    signal_log = pyqtSignal(str)
    signal_result = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.operation = None
        self.data = None
        self.password = None
        self.protect = False

    def set_operation(self, op, **kwargs):
        self.operation = op
        self.data = kwargs.get('data')
        self.password = kwargs.get('password')
        self.protect = kwargs.get('protect', False)

    def run(self):
        try:
            with nfc.ContactlessFrontend('usb') as clf:
                if not clf:
                    self.signal_log.emit("❌ 未检测到读卡器，请连接ACR122U等兼容设备")
                    return

                tag = clf.connect(rdwr={'on-connect': lambda tag: False})
                if not tag:
                    self.signal_log.emit("🔍 请将NTAG标签靠近读卡器...")
                    return

                if not isinstance(tag, tt2.Type2Tag):
                    self.signal_log.emit("⚠️ 不支持的标签类型，仅限NTAG系列")
                    return

                result = {'uid': tag.identifier.hex(), 'type': 'NTAG'}
                
                if self.operation == 'read':
                    self.read_tag(tag, result)
                elif self.operation == 'write':
                    self.write_tag(tag, result)
                elif self.operation == 'format':
                    self.format_tag(tag, result)
                elif self.operation == 'protect':
                    self.set_protection(tag, result)
                
                self.signal_result.emit(result)

        except Exception as e:
            self.signal_log.emit(f"❌ 操作失败: {str(e)}")

    def read_tag(self, tag, result):
        """读取标签完整数据"""
        try:
            # 读取前16个块（NTAG213/215/216通用区域）
            data = []
            for block in range(16):
                try:
                    data.append(tag.read(block))
                except:
                    break
            hex_data = [binascii.hexlify(block).decode() for block in data]
            
            result.update({
                'data': hex_data,
                'message': "读取成功",
                'status': 'success'
            })
            self.signal_log.emit("✅ NTAG数据读取完成")
            
        except Exception as e:
            self.signal_log.emit(f"❌ 读取失败: {str(e)}")

    def write_tag(self, tag, result):
        """写入数据到标签"""
        if not self.data:
            self.signal_log.emit("⚠️ 请输入要写入的数据")
            return

        try:
            # 转换为字节数组
            data_bytes = bytearray.fromhex(self.data.replace(' ', ''))
            
            # NTAG写入必须以4字节为块
            if len(data_bytes) % 4 != 0:
                padding = 4 - (len(data_bytes) % 4)
                data_bytes.extend([0xFF] * padding)
            
            # 从块4开始写入（避开厂商预留区）
            for i, chunk in enumerate([data_bytes[i:i+4] for i in range(0, len(data_bytes), 4)]):

                tag.write(4 + i, chunk)
            
            result.update({
                'message': f"写入{len(data_bytes)}字节成功",
                'status': 'success'
            })
            self.signal_log.emit("✅ 数据写入完成")
            
        except Exception as e:
            self.signal_log.emit(f"❌ 写入失败: {str(e)}")

    def format_tag(self, tag, result):
        """格式化标签（重置为出厂状态）"""
        try:
            # 将用户数据区全部写0
            for block in range(4, 16):
                tag.write(block, bytearray([0, 0, 0, 0]))
            
            # 重置密码保护（如果支持）
            if hasattr(tag, 'protect'):
                tag.protect(False, bytearray([0xFF]*4))
            
            result.update({
                'message': "格式化完成",
                'status': 'success'
            })
            self.signal_log.emit("✅ NTAG已恢复出厂设置")
            
        except Exception as e:
            self.signal_log.emit(f"❌ 格式化失败: {str(e)}")

    def set_protection(self, tag, result):
        """设置密码保护（NTAG424专属功能）"""
        try:
            if not self.password or len(self.password) != 8:
                self.signal_log.emit("⚠️ 密码必须为4字节十六进制(8字符)")
                return

            # 转换为字节数组
            pwd = bytearray.fromhex(self.password)
            
            # 尝试设置保护
            if hasattr(tag, 'protect'):
                tag.protect(self.protect, pwd)
                action = "启用" if self.protect else "禁用"
                result.update({
                    'message': f"密码保护{action}成功",
                    'status': 'success'
                })
                self.signal_log.emit(f"✅ 已{action}密码保护")
            else:
                self.signal_log.emit("⚠️ 当前标签不支持密码保护功能")
                
        except Exception as e:
            self.signal_log.emit(f"❌ 密码设置失败: {str(e)}")

class NTAGTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NTAG高级工具 - Windows版")
        self.setGeometry(100, 100, 800, 600)
        
        # 初始化工作线程
        self.worker = NTAGOperations()
        self.worker.signal_log.connect(self.update_log)
        self.worker.signal_result.connect(self.show_result)
        
        # 创建主界面
        self.create_main_tabs()
        self.create_status_bar()
        
        # 当前标签信息
        self.current_tag = None

    def create_main_tabs(self):
        """创建功能选项卡"""
        tabs = QTabWidget()
        
        # 标签读取页
        read_tab = QWidget()
        self.setup_read_tab(read_tab)
        tabs.addTab(read_tab, "读取数据")
        
        # 数据写入页
        write_tab = QWidget()
        self.setup_write_tab(write_tab)
        tabs.addTab(write_tab, "写入数据")
        
        # 格式化页
        format_tab = QWidget()
        self.setup_format_tab(format_tab)
        tabs.addTab(format_tab, "格式化")
        
        # 密码保护页
        protect_tab = QWidget()
        self.setup_protect_tab(protect_tab)
        tabs.addTab(protect_tab, "密码保护")
        
        # 日志显示区
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        
        # 主布局
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.addWidget(tabs)
        layout.addWidget(QLabel("操作日志:"))
        layout.addWidget(self.log_display)

        self.setCentralWidget(central_widget)
        
        #container = QWidget()
        #container.setLayout(layout)
        #self.setCentralWidget(container)
        

    def setup_read_tab(self, tab):
        """读取标签页布局"""
        layout = QVBoxLayout()
        
        # 标签信息显示
        self.tag_info = QTextEdit()
        self.tag_info.setReadOnly(True)
        self.tag_info.setPlaceholderText("标签信息将显示在这里...")
        
        # 操作按钮
        btn_read = QPushButton("读取NTAG数据 (F5)")
        btn_read.setShortcut("F5")
        btn_read.clicked.connect(lambda: self.start_operation('read'))
        
        btn_export = QPushButton("导出数据...")
        btn_export.clicked.connect(self.export_data)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_read)
        btn_layout.addWidget(btn_export)
        
        layout.addWidget(QLabel("NTAG数据读取:"))
        layout.addWidget(self.tag_info)
        layout.addLayout(btn_layout)
        tab.setLayout(layout)

    def setup_write_tab(self, tab):
        """写入数据页布局"""
        layout = QVBoxLayout()
        
        # 数据输入
        self.write_data = QTextEdit()
        self.write_data.setPlaceholderText("输入十六进制数据（如 01020304 A1B2C3D4）")
        
        # 文件导入
        btn_import = QPushButton("从文件导入...")
        btn_import.clicked.connect(self.import_data)
        
        # 写入按钮
        btn_write = QPushButton("写入数据 (F6)")
        btn_write.setShortcut("F6")
        btn_write.clicked.connect(lambda: self.start_operation('write', 
                                data=self.write_data.toPlainText()))
        
        # 布局
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("写入数据:"))
        file_layout.addWidget(btn_import)
        
        layout.addLayout(file_layout)
        layout.addWidget(self.write_data)
        layout.addWidget(btn_write)
        tab.setLayout(layout)

    def setup_format_tab(self, tab):
        """格式化页布局"""
        layout = QVBoxLayout()
        
        lbl_warning = QLabel("⚠️ 格式化将清除所有用户数据！")
        lbl_warning.setStyleSheet("color: red; font-weight: bold;")
        
        btn_format = QPushButton("格式化NTAG (F7)")
        btn_format.setShortcut("F7")
        btn_format.clicked.connect(lambda: self.start_operation('format'))
        
        layout.addWidget(lbl_warning)
        layout.addWidget(QLabel("将标签恢复出厂设置:"))
        layout.addWidget(btn_format)
        layout.addStretch()
        tab.setLayout(layout)

    def setup_protect_tab(self, tab):
        """密码保护页布局"""
        layout = QVBoxLayout()
        
        # 密码输入
        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("输入4字节十六进制密码（如 FFAABBCC）")
        self.pwd_input.setMaxLength(8)
        
        # 保护选项
        self.protect_check = QCheckBox("启用写保护")
        self.protect_check.setChecked(True)
        
        # 操作按钮
        btn_set = QPushButton("设置密码 (F8)")
        btn_set.setShortcut("F8")
        btn_set.clicked.connect(self.set_protection)
        
        # 布局
        form_layout = QVBoxLayout()
        form_layout.addWidget(QLabel("密码设置（仅NTAG424支持）:"))
        form_layout.addWidget(self.pwd_input)
        form_layout.addWidget(self.protect_check)
        form_layout.addWidget(btn_set)
        
        layout.addLayout(form_layout)
        layout.addStretch()
        tab.setLayout(layout)

    def create_status_bar(self):
        """创建状态栏"""
        self.status_bar = QLabel("就绪 | 请将NTAG标签靠近读卡器")
        self.status_bar.setAlignment(Qt.AlignCenter)
        self.status_bar.setStyleSheet("background: #EEE; padding: 3px;")
        # self.layout().addWidget(self.status_bar)

        # 正确设置状态栏
        self.statusBar().addWidget(self.status_bar, 1)  # 使用QMainWindow自带的状态栏

    def start_operation(self, operation, **kwargs):
        """启动操作线程"""
        if self.worker.isRunning():
            QMessageBox.warning(self, "警告", "当前有操作正在进行，请稍候")
            return
        
        self.worker.set_operation(operation, **kwargs)
        self.worker.start()
        self.status_bar.setText(f"操作中: {operation}...")

    def set_protection(self):
        """处理密码保护设置"""
        pwd = self.pwd_input.text().strip()
        if not pwd or len(pwd) != 8:
            QMessageBox.warning(self, "输入错误", "密码必须为4字节十六进制(8字符)")
            return
        
        try:
            # 验证是否为合法十六进制
            bytearray.fromhex(pwd)
        except:
            QMessageBox.warning(self, "输入错误", "包含非法十六进制字符")
            return
        
        self.start_operation('protect', 
                           password=pwd,
                           protect=self.protect_check.isChecked())

    def import_data(self):
        """从文件导入数据"""
        path, _ = QFileDialog.getOpenFileName(self, "选择数据文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if path:
            try:
                with open(path, 'r') as f:
                    data = f.read()
                    self.write_data.setPlainText(data)
                    self.update_log(f"已导入文件: {path}")
            except Exception as e:
                self.update_log(f"❌ 文件导入失败: {str(e)}")

    def export_data(self):
        """导出标签数据到文件"""
        if not self.current_tag or 'data' not in self.current_tag:
            QMessageBox.warning(self, "无数据", "请先读取标签数据")
            return
        
        path, _ = QFileDialog.getSaveFileName(self, "保存数据文件", "ntag_data.txt", "文本文件 (*.txt);;所有文件 (*)")
        if path:
            try:
                with open(path, 'w') as f:
                    f.write("\n".join(self.current_tag['data']))
                self.update_log(f"数据已导出到: {path}")
            except Exception as e:
                self.update_log(f"❌ 导出失败: {str(e)}")

    def update_log(self, message):
        """更新日志显示"""
        self.log_display.append(message)
        self.log_display.verticalScrollBar().setValue(
            self.log_display.verticalScrollBar().maximum())

    def show_result(self, result):
        """显示操作结果"""
        self.current_tag = result
        self.status_bar.setText(f"就绪 | {result.get('message', '操作完成')}")
        
        if self.worker.operation == 'read' and 'data' in result:
            self.tag_info.clear()
            self.tag_info.append(f"UID: {result['uid']}")
            self.tag_info.append("\n数据区块 (十六进制):")
            for i, block in enumerate(result['data']):
                self.tag_info.append(f"块{i:02d}: {block.upper()}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Windows平台优化
    if sys.platform == 'win32':
        import ctypes
        # 设置为高DPI适配
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    
    # 检查依赖
    try:
        import nfc
        import binascii
    except ImportError:
        QMessageBox.critical(None, "缺少依赖", 
            "请先安装以下库：\n\npip install nfcpy pyqt5")
        sys.exit(1)
    
    # 检查读卡器驱动
    try:
        nfc.ContactlessFrontend('usb')
    except Exception as e:
        QMessageBox.warning(None, "驱动检测", 
            f"请确保已安装ACR122U驱动\n\n错误详情: {str(e)}")
    
    window = NTAGTool()
    window.show()
    sys.exit(app.exec_())