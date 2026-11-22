import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                            QLabel, QPushButton, QTextEdit, QComboBox, 
                            QGroupBox, QHBoxLayout)
from PyQt5.QtCore import QThread, pyqtSignal
import nfc
from nfc.tag import tt2

class NFCScanner(QThread):
    signal_update = pyqtSignal(dict)  # 传递检测结果的字典
    signal_error = pyqtSignal(str)

    def run(self):
        try:
            with nfc.ContactlessFrontend(self.interface) as clf:
                result = {'status': 'connected', 'interface': self.interface}
                self.signal_update.emit(result)
                
                # 尝试读取标签
                tag = clf.connect(rdwr={'on-connect': lambda tag: False})
                if tag:
                    result.update(self.parse_tag_info(tag))
                    self.signal_update.emit(result)
        except Exception as e:
            self.signal_error.emit(f"硬件错误: {str(e)}")

    def parse_tag_info(self, tag):
        """解析不同NTAG类型的详细信息"""
        info = {
            'uid': tag.identifier.hex(),
            'type': tag.type,
            'product': str(tag.product),
            'is_ntag': False,
            'ntag_type': None,
            'memory_size': '未知',
            'ndef_support': bool(tag.ndef)
        }

        # 检测NTAG具体型号
        if isinstance(tag, tt2.Type2Tag):
            try:
                version_byte = tag.read()[12]
                if version_byte == 0x12:  # NTAG213
                    info.update({'is_ntag': True, 'ntag_type': 'NTAG213', 'memory_size': '144字节'})
                elif version_byte == 0x3E:  # NTAG215
                    info.update({'is_ntag': True, 'ntag_type': 'NTAG215', 'memory_size': '504字节'})
                elif version_byte == 0x6D:  # NTAG216
                    info.update({'is_ntag': True, 'ntag_type': 'NTAG216', 'memory_size': '888字节'})
                elif version_byte == 0x72:  # NTAG424
                    info.update({'is_ntag': True, 'ntag_type': 'NTAG424', 'memory_size': '888字节'})
            except:
                pass

        return info

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NTAG系列读卡器兼容性检测")
        self.setMinimumSize(600, 500)
        
        # 主布局
        main_layout = QVBoxLayout()
        
        # 设备选择区域
        device_group = QGroupBox("读卡器设置")
        device_layout = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.addItems(['auto', 'usb', 'com:', 'tty:', 'ttyS:'])
        self.refresh_btn = QPushButton("刷新接口")
        self.refresh_btn.clicked.connect(self.refresh_interfaces)
        device_layout.addWidget(QLabel("接口类型:"))
        device_layout.addWidget(self.device_combo, stretch=1)
        device_layout.addWidget(self.refresh_btn)
        device_group.setLayout(device_layout)
        
        # NTAG信息区域
        self.info_group = QGroupBox("标签信息")
        info_layout = QVBoxLayout()
        self.info_display = QTextEdit()
        self.info_display.setReadOnly(True)
        info_layout.addWidget(self.info_display)
        self.info_group.setLayout(info_layout)
        self.info_group.setVisible(False)
        
        # 操作按钮
        self.scan_btn = QPushButton("开始检测 (Ctrl+S)")
        self.scan_btn.setShortcut("Ctrl+S")
        self.scan_btn.clicked.connect(self.start_scan)
        
        # 状态栏
        self.status_label = QLabel("准备就绪")
        
        # 组装界面
        main_layout.addWidget(device_group)
        main_layout.addWidget(self.info_group)
        main_layout.addWidget(self.scan_btn)
        main_layout.addWidget(self.status_label)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        
        # 扫描线程
        self.scanner = None
    
    def refresh_interfaces(self):
        """刷新可用接口列表"""
        self.device_combo.clear()
        self.device_combo.addItems(['auto', 'usb', 'com:', 'tty:', 'ttyS:'])
        self.status_label.setText("接口列表已刷新")
    
    def start_scan(self):
        if self.scanner and self.scanner.isRunning():
            self.scanner.terminate()
            
        self.info_display.clear()
        self.info_group.setVisible(False)
        self.status_label.setText("正在检测读卡器...")
        
        self.scanner = NFCScanner()
        self.scanner.interface = self.device_combo.currentText()
        self.scanner.signal_update.connect(self.update_info)
        self.scanner.signal_error.connect(self.show_error)
        self.scanner.finished.connect(self.scan_finished)
        self.scanner.start()
    
    def update_info(self, info):
        """更新标签信息显示"""
        self.info_group.setVisible(True)
        
        if info.get('status') == 'connected':
            self.status_label.setText(f"已连接到 {info['interface']} 接口")
            self.info_display.append("🟢 读卡器连接成功")
            self.info_display.append("请将NTAG标签靠近读卡器...")
            return
        
        # 显示标签基本信息
        self.info_display.clear()
        self.info_display.append("🔍 检测到NFC标签")
        self.info_display.append(f"UID: {info['uid']}")
        self.info_display.append(f"类型: {info['type']}")
        
        # NTAG特定信息
        if info['is_ntag']:
            self.info_display.append("\n🟢 NTAG标签检测成功")
            self.info_display.append(f"型号: {info['ntag_type']}")
            self.info_display.append(f"存储容量: {info['memory_size']}")
            self.info_display.append(f"NDEF支持: {'是' if info['ndef_support'] else '否'}")
            
            # 显示各型号特性
            if info['ntag_type'] == 'NTAG213':
                self.info_display.append("\n特性: 适合小型数据存储，144字节用户内存")
            elif info['ntag_type'] == 'NTAG215':
                self.info_display.append("\n特性: 大容量，适合游戏卡牌等应用")
            elif info['ntag_type'] == 'NTAG216':
                self.info_display.append("\n特性: 最大容量，支持复杂数据")
            elif info['ntag_type'] == 'NTAG424':
                self.info_display.append("\n特性: 加密通信，安全支付场景")
        else:
            self.info_display.append("\n⚠️ 非NTAG标签或不被支持的NTAG型号")
    
    def scan_finished(self):
        self.status_label.setText("检测完成")
    
    def show_error(self, error):
        self.info_display.append(f"\n❌ {error}")
        self.status_label.setText("检测失败")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置中文显示
    try:
        from PyQt5.QtCore import QTranslator
        translator = QTranslator()
        translator.load("qt_zh_CN.qm")
        app.installTranslator(translator)
    except:
        pass
    
    # 检查依赖
    try:
        import nfc
    except ImportError:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(None, "缺少依赖", 
            "请先安装以下库：\n\npip install nfcpy pyqt5")
        sys.exit(1)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())