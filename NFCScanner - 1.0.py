import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                            QLabel, QPushButton, QTextEdit, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal
import nfc

class NFCScanner(QThread):
    signal_result = pyqtSignal(str)
    signal_error = pyqtSignal(str)

    def run(self):
        try:
            with nfc.ContactlessFrontend('usb') as clf:
                self.signal_result.emit("✅ 读卡器连接成功，正在检测NTAG216支持...")
                
                # 尝试读取标签
                tag = clf.connect(rdwr={'on-connect': lambda tag: False})
                if tag:
                    info = f"检测到标签:\nUID: {tag.identifier.hex()}\n类型: {tag.type}"
                    self.signal_result.emit(info)
                    
                    if tag.type == "Type2Tag":
                        self.signal_result.emit("🎉 支持NTAG216标签！")
                    else:
                        self.signal_result.emit("⚠️ 检测到标签但不支持NTAG216")
                else:
                    self.signal_result.emit("🔍 未检测到标签，请将NTAG216靠近读卡器")
        except Exception as e:
            self.signal_error.emit(f"❌ 错误: {str(e)}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NTAG216读卡器兼容性检测")
        self.setGeometry(100, 100, 500, 400)
        
        # 主布局
        layout = QVBoxLayout()
        
        # 设备选择
        self.device_label = QLabel("选择读卡器接口:")
        self.device_combo = QComboBox()
        self.device_combo.addItems(['usb', 'com:', 'tty:'])  # 常见接口
        
        # 状态显示
        self.status_label = QLabel("状态: 等待检测...")
        self.result_display = QTextEdit()
        self.result_display.setReadOnly(True)
        
        # 操作按钮
        self.scan_btn = QPushButton("开始检测")
        self.scan_btn.clicked.connect(self.start_scan)
        
        # 组装界面
        layout.addWidget(self.device_label)
        layout.addWidget(self.device_combo)
        layout.addWidget(self.status_label)
        layout.addWidget(self.result_display)
        layout.addWidget(self.scan_btn)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        
        # 扫描线程
        self.scanner = None
    
    def start_scan(self):
        if self.scanner and self.scanner.isRunning():
            return
            
        self.result_display.clear()
        self.status_label.setText("状态: 检测中...")
        
        interface = self.device_combo.currentText()
        self.result_display.append(f"尝试通过 {interface} 接口连接读卡器...")
        
        self.scanner = NFCScanner()
        self.scanner.signal_result.connect(self.update_result)
        self.scanner.signal_error.connect(self.show_error)
        self.scanner.finished.connect(lambda: self.status_label.setText("状态: 检测完成"))
        self.scanner.start()
    
    def update_result(self, message):
        self.result_display.append(message)
    
    def show_error(self, error):
        self.result_display.append(error)
        self.status_label.setText("状态: 检测失败")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 检查nfcpy是否安装
    try:
        import nfc
    except ImportError:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(None, "缺少依赖", "请先安装nfcpy库：pip install nfcpy")
        sys.exit(1)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())