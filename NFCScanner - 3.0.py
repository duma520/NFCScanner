import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                            QLabel, QPushButton, QTextEdit, QComboBox,
                            QGroupBox, QHBoxLayout, QTableWidget, 
                            QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import nfc
# from nfc.clf import Device
import usb.core
import serial.tools.list_ports

class NFCScanner(QThread):
    signal_update = pyqtSignal(dict)
    signal_error = pyqtSignal(str)

    def __init__(self, interface):
        super().__init__()
        self.interface = interface
        self.supported_readers = {
            'ACS ACR122U': self.check_acr122u,
            'PN532': self.check_pn532,
            '手机NFC': self.check_phone_nfc,
            'Generic USB': self.check_generic_usb
        }

    def run(self):
        try:
            result = {'reader_type': '未知', 'status': '检测中'}
            self.signal_update.emit(result)

            # 尝试识别具体读卡器型号
            with nfc.ContactlessFrontend(self.interface) as clf:
                reader_name = str(clf.device)
                result['reader_name'] = reader_name

                # 调用各厂商专用检测方法
                for name, checker in self.supported_readers.items():
                    if checker(clf):
                        result['reader_type'] = name
                        break

                # 通用标签检测
                if clf:
                    tag = clf.connect(rdwr={'on-connect': lambda tag: False})
                    if tag:
                        result.update(self.parse_tag_info(tag))
                        result['status'] = '标签已识别'
                    else:
                        result['status'] = '就绪（未检测到标签）'
                
                self.signal_update.emit(result)

        except Exception as e:
            self.signal_error.emit(f"硬件错误: {str(e)}")

    def check_acr122u(self, clf):
        """检测ACS ACR122U读卡器"""
        return 'ACR122' in str(clf.device)

    def check_pn532(self, clf):
        """检测PN532芯片读卡器"""
        return 'PN532' in str(clf.device)

    def check_phone_nfc(self, clf):
        """检测手机NFC模拟读卡器"""
        return 'android' in str(clf.device).lower()

    def check_generic_usb(self, clf):
        """检测通用USB读卡器"""
        return 'USB' in str(clf.device)

    def parse_tag_info(self, tag):
        """解析标签信息（增强版）"""
        info = {
            'tag_type': tag.type,
            'uid': tag.identifier.hex(),
            'is_ndef': bool(tag.ndef),
            'details': {}
        }

        # NTAG系列检测
        if isinstance(tag, nfc.tag.tt2.Type2Tag):
            try:
                version_byte = tag.read()[12]
                ntag_types = {
                    0x12: ('NTAG213', '144字节'),
                    0x3E: ('NTAG215', '504字节'),
                    0x6D: ('NTAG216', '888字节'),
                    0x72: ('NTAG424', '888字节+加密')
                }
                if version_byte in ntag_types:
                    info['details'].update({
                        'type': 'NTAG',
                        'model': ntag_types[version_byte][0],
                        'memory': ntag_types[version_byte][1]
                    })
            except:
                pass

        # 其他常见标签类型
        elif tag.type == 'Type4Tag':
            info['details'].update({
                'type': 'Type 4 (如DESFire)',
                'model': 'ISO/IEC 14443-4'
            })

        return info

class ReaderDetectionWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("多功能读卡器兼容性检测")
        self.setMinimumSize(800, 600)

        # 主布局
        main_layout = QVBoxLayout()

        # 设备检测区
        self.setup_reader_detection_group(main_layout)

        # 标签信息区
        self.setup_tag_info_group(main_layout)

        # 状态栏
        self.status_bar = QLabel("准备就绪 | 请连接读卡器后点击扫描")
        self.status_bar.setAlignment(Qt.AlignCenter)
        
        main_layout.addWidget(self.status_bar)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def setup_reader_detection_group(self, layout):
        """读卡器检测区域设置"""
        group = QGroupBox("读卡器检测")
        grid = QVBoxLayout()

        # 接口选择
        self.interface_combo = QComboBox()
        self.refresh_interfaces()
        self.scan_btn = QPushButton("扫描设备 (F5)")
        self.scan_btn.setShortcut("F5")
        self.scan_btn.clicked.connect(self.start_scan)

        # 读卡器信息表格
        self.reader_table = QTableWidget()
        self.reader_table.setColumnCount(3)
        self.reader_table.setHorizontalHeaderLabels(["属性", "值", "状态"])
        self.reader_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.reader_table.setEditTriggers(QTableWidget.NoEditTriggers)

        # 布局
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("接口:"))
        hbox.addWidget(self.interface_combo, stretch=1)
        hbox.addWidget(self.scan_btn)
        
        grid.addLayout(hbox)
        grid.addWidget(self.reader_table)
        group.setLayout(grid)
        layout.addWidget(group)

    def setup_tag_info_group(self, layout):
        """标签信息区域设置"""
        group = QGroupBox("标签信息")
        self.tag_info_display = QTextEdit()
        self.tag_info_display.setReadOnly(True)
        
        vbox = QVBoxLayout()
        vbox.addWidget(self.tag_info_display)
        group.setLayout(vbox)
        group.setVisible(False)
        layout.addWidget(group)

    def refresh_interfaces(self):
        """刷新可用接口列表"""
        self.interface_combo.clear()
        
        # 自动检测常见接口
        interfaces = ['auto']
        
        # 检测USB设备
        if usb.core.find(find_all=True):
            interfaces.extend(['usb:%d' % i for i in range(3)])
        
        # 检测串口设备
        ports = [p.device for p in serial.tools.list_ports.comports()]
        interfaces.extend(ports)
        
        self.interface_combo.addItems(interfaces)

    def start_scan(self):
        """启动扫描线程"""
        if hasattr(self, 'scanner') and self.scanner.isRunning():
            return

        self.reader_table.setRowCount(0)
        self.tag_info_display.clear()
        self.status_bar.setText("正在检测硬件...")

        self.scanner = NFCScanner(self.interface_combo.currentText())
        self.scanner.signal_update.connect(self.update_reader_info)
        self.scanner.signal_error.connect(self.show_error)
        self.scanner.start()

    def update_reader_info(self, info):
        """更新读卡器信息显示"""
        self.reader_table.setRowCount(0)
        
        # 显示读卡器基本信息
        self.add_table_row("设备名称", info.get('reader_name', '未知'), "✅" if info.get('reader_name') else "❌")
        self.add_table_row("设备类型", info.get('reader_type', '未知'), "✅" if info.get('reader_type') != '未知' else "⚠️")
        self.add_table_row("连接状态", info.get('status', '未知'), "✅" if '就绪' in info.get('status', '') else "🔍")

        # 显示标签信息（如果检测到）
        if 'tag_type' in info:
            self.centralWidget().findChild(QGroupBox, "标签信息").setVisible(True)
            self.tag_info_display.append(f"🔍 检测到 {info['tag_type']} 标签")
            self.tag_info_display.append(f"UID: {info['uid']}")
            self.tag_info_display.append(f"NDEF支持: {'是' if info['is_ndef'] else '否'}")
            
            if info['details']:
                self.tag_info_display.append("\n详细信息:")
                for k, v in info['details'].items():
                    self.tag_info_display.append(f"{k}: {v}")

        self.status_bar.setText(f"就绪 | {info.get('status', '')}")

    def add_table_row(self, key, value, status_icon=""):
        """添加表格行辅助函数"""
        row = self.reader_table.rowCount()
        self.reader_table.insertRow(row)
        self.reader_table.setItem(row, 0, QTableWidgetItem(key))
        self.reader_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.reader_table.setItem(row, 2, QTableWidgetItem(status_icon))

    def show_error(self, error):
        """显示错误信息"""
        self.status_bar.setText(f"错误: {error}")
        self.add_table_row("错误信息", error, "❌")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 检查依赖
    missing = []
    for lib in ['nfc', 'usb', 'serial']:
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)
    
    if missing:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(None, "缺少依赖",
            f"请先安装以下库：\n\npip install {' '.join(missing)}")
        sys.exit(1)
    
    window = ReaderDetectionWindow()
    window.show()
    sys.exit(app.exec_())