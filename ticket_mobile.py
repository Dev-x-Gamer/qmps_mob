"""
Patient Token Slip - Mobile (Android) version
Kivy UI + classic Bluetooth (SPP/RFCOMM) ESC/POS printing via pyjnius.

Desktop testing: `python main.py` (printing is simulated in the console).
"""
import json
import os
import threading
import time
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ListProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.utils import get_color_from_hex as hex_
from kivy.utils import platform

IS_ANDROID = platform == "android"
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"  # standard serial-port UUID

if not IS_ANDROID:
    Window.size = (400, 780)  # phone-shaped window for desktop testing


# --------------------------------------------------------------------------
# Bluetooth printer (Android only)
# --------------------------------------------------------------------------
class BluetoothPrinter:
    """Sends raw ESC/POS bytes to a paired classic-Bluetooth printer."""

    @staticmethod
    def request_permissions():
        if not IS_ANDROID:
            return
        from android.permissions import request_permissions

        request_permissions(
            [
                "android.permission.BLUETOOTH_CONNECT",
                "android.permission.BLUETOOTH_SCAN",
                "android.permission.ACCESS_FINE_LOCATION",
            ]
        )

    @staticmethod
    def paired_devices():
        """Return list of (name, address) for paired devices."""
        if not IS_ANDROID:
            return [("Demo Printer (desktop test)", "00:00:00:00:00:00")]
        from jnius import autoclass

        adapter = autoclass("android.bluetooth.BluetoothAdapter").getDefaultAdapter()
        if adapter is None:
            raise RuntimeError("This phone has no Bluetooth.")
        if not adapter.isEnabled():
            raise RuntimeError("Bluetooth is OFF. Please turn it on.")
        devices = adapter.getBondedDevices().toArray()
        return [(d.getName() or "Unknown", d.getAddress()) for d in devices]

    @staticmethod
    def send(address, data: bytes):
        if not IS_ANDROID:
            print("---- [SIMULATED PRINT] ----")
            print(data.decode("cp437", errors="ignore"))
            return
        from jnius import autoclass

        BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
        UUID = autoclass("java.util.UUID")

        adapter = BluetoothAdapter.getDefaultAdapter()
        if adapter is None or not adapter.isEnabled():
            raise RuntimeError("Bluetooth is OFF. Please turn it on.")

        device = adapter.getRemoteDevice(address)
        adapter.cancelDiscovery()  # discovery slows/blocks connections

        sock = None
        try:
            try:
                sock = device.createRfcommSocketToServiceRecord(UUID.fromString(SPP_UUID))
                sock.connect()
            except Exception:
                # Fallback used by many cheap printers
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
                sock = device.getClass().getMethod(
                    "createRfcommSocket", autoclass("java.lang.Integer").TYPE
                ).invoke(device, 1)
                sock.connect()

            out = sock.getOutputStream()
            # send in small chunks - tiny printer buffers overflow easily
            for i in range(0, len(data), 512):
                out.write(data[i : i + 512])
                out.flush()
                time.sleep(0.05)
            time.sleep(0.5)  # let the printer finish before closing
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass


def build_ticket(number: int, title: str, footer: str) -> bytes:
    """Build an ESC/POS receipt for a 58mm printer (32 chars/line)."""
    ESC, GS = b"\x1b", b"\x1d"
    now = datetime.now().strftime("%d/%m/%Y - %I:%M:%S %p")

    d = ESC + b"@"  # initialise
    d += ESC + b"a\x01"  # centre
    d += ESC + b"E\x01" + title.encode("cp437", "replace") + b"\n" + ESC + b"E\x00"
    d += b"--------------------------------\n"
    d += GS + b"!\x33"  # 4x width, 4x height
    d += f"{number:03d}".encode() + b"\n"
    d += GS + b"!\x00"
    d += b"--------------------------------\n"
    d += footer.encode("cp437", "replace") + b"\n"
    d += now.encode() + b"\n"
    d += b"\n\n\n\n"  # feed so slip clears the tear bar
    return d


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
KV = """
#:import hex kivy.utils.get_color_from_hex

<RoundButton>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    color: 1, 1, 1, 1
    bold: True
    canvas.before:
        Color:
            rgba: (self.bg[0]*0.8, self.bg[1]*0.8, self.bg[2]*0.8, 1) if self.state == 'down' else self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(18)]

<Root>:
    orientation: 'vertical'
    padding: 0
    spacing: dp(14)
    canvas.before:
        Color:
            rgba: hex('#f0f4f8')
        Rectangle:
            pos: self.pos
            size: self.size

    # ---------- header ----------
    BoxLayout:
        orientation: 'vertical'
        size_hint_y: None
        height: dp(120)
        padding: dp(10), dp(24), dp(10), dp(8)
        canvas.before:
            Color:
                rgba: hex('#2980b9')
            Rectangle:
                pos: self.pos
                size: self.size
        Label:
            text: app.title_text
            font_size: sp(24)
            bold: True
        Label:
            text: app.clock_text
            font_size: sp(14)
            bold: True

    # ---------- printer status (tap to change) ----------
    RoundButton:
        id: printer_btn
        text: app.printer_text
        font_size: sp(14)
        size_hint: 0.92, None
        height: dp(44)
        pos_hint: {'center_x': .5}
        bg: hex('#34495e')
        on_release: app.choose_printer()

    Label:
        text: 'Current Ticket Number'
        color: 0.1, 0.1, 0.1, 1
        bold: True
        font_size: sp(18)
        size_hint_y: None
        height: dp(30)

    # ---------- ticket card ----------
    BoxLayout:
        size_hint: 0.92, None
        height: dp(170)
        pos_hint: {'center_x': .5}
        canvas.before:
            Color:
                rgba: 1, 1, 1, 1
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(20)]
            Color:
                rgba: hex('#2980b9')
            Line:
                rounded_rectangle: (self.x, self.y, self.width, self.height, dp(20))
                width: dp(2)
        Label:
            text: app.ticket_text
            color: 0, 0, 0, 1
            bold: True
            font_size: sp(96)

    Label:
        text: app.status_text
        color: hex(app.status_color)
        font_size: sp(14)
        size_hint_y: None
        height: dp(24)

    # ---------- main action ----------
    RoundButton:
        text: 'NEW TICKET + PRINT'
        font_size: sp(22)
        size_hint: 0.92, None
        height: dp(84)
        pos_hint: {'center_x': .5}
        bg: hex('#27ae60')
        on_release: app.new_ticket()

    # ---------- secondary actions ----------
    BoxLayout:
        size_hint: 0.92, None
        height: dp(56)
        pos_hint: {'center_x': .5}
        spacing: dp(12)
        RoundButton:
            text: 'Reprint'
            font_size: sp(16)
            bg: hex('#e67e22')
            on_release: app.reprint()
        RoundButton:
            text: app.reset_text
            font_size: sp(16)
            bg: hex('#c0392b')
            on_release: app.confirm_reset()

    Widget:
"""


class RoundButton(Button):
    bg = ListProperty([0.2, 0.2, 0.2, 1])


class Root(BoxLayout):
    pass


class TokenApp(App):
    title_text = StringProperty("Patient Token Slip")
    clock_text = StringProperty("")
    ticket_text = StringProperty("0")
    reset_text = StringProperty("Reset (0)")
    printer_text = StringProperty("Tap to select Bluetooth printer")
    status_text = StringProperty("")
    status_color = StringProperty("#7f8c8d")

    # ---------- storage ----------
    def build(self):
        self.title = "Waris Software Tech"
        Builder.load_string(KV)
        self.cfg_path = os.path.join(self.user_data_dir, "token_data.json")
        self.cfg = {"counter": 0, "printer_addr": "", "printer_name": ""}
        self.load()
        self.print_lock = threading.Lock()
        BluetoothPrinter.request_permissions()
        Clock.schedule_interval(self.tick, 1)
        self.tick(0)
        self.refresh()
        return Root()

    def load(self):
        try:
            with open(self.cfg_path, "r") as f:
                self.cfg.update(json.load(f))
        except Exception:
            pass

    def save(self):
        try:
            with open(self.cfg_path, "w") as f:
                json.dump(self.cfg, f)
        except Exception as e:
            self.set_status(f"Could not save: {e}", error=True)

    # ---------- ui helpers ----------
    def tick(self, _dt):
        self.clock_text = datetime.now().strftime("%d-%m-%Y  |  %I:%M:%S %p")

    def refresh(self):
        n = self.cfg["counter"]
        self.ticket_text = str(n)
        self.reset_text = f"Reset ({n})"
        if self.cfg["printer_addr"]:
            self.printer_text = f"Printer: {self.cfg['printer_name']}  (tap to change)"
        else:
            self.printer_text = "Tap to select Bluetooth printer"

    @mainthread
    def set_status(self, msg, error=False, ok=False):
        self.status_text = msg
        self.status_color = "#c0392b" if error else ("#27ae60" if ok else "#7f8c8d")

    # ---------- actions ----------
    def new_ticket(self):
        if not self.cfg["printer_addr"]:
            self.set_status("Select a printer first", error=True)
            self.choose_printer(then_print=True)
            return
        self.cfg["counter"] += 1
        self.save()
        self.refresh()
        self.print_number(self.cfg["counter"])

    def reprint(self):
        if self.cfg["counter"] <= 0:
            self.set_status("Nothing to reprint yet", error=True)
            return
        if not self.cfg["printer_addr"]:
            self.choose_printer(then_print=False)
            return
        self.print_number(self.cfg["counter"])

    def print_number(self, number):
        if self.print_lock.locked():
            self.set_status("Printer busy, please wait...")
            return
        self.set_status(f"Printing {number:03d}...")
        threading.Thread(target=self._print_worker, args=(number,), daemon=True).start()

    def _print_worker(self, number):
        with self.print_lock:
            try:
                data = build_ticket(number, self.title_text.upper(), "WAIT YOUR NUMBER")
                BluetoothPrinter.send(self.cfg["printer_addr"], data)
                self.set_status(f"Ticket {number:03d} printed", ok=True)
            except Exception as e:
                self.set_status(f"Print failed - tap Reprint. ({e})", error=True)

    # ---------- reset ----------
    def confirm_reset(self):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(12))
        box.add_widget(Label(text="Are you sure you want to reset\nthe counter to 0?", halign="center"))
        row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        pop = Popup(title="Reset", content=box, size_hint=(0.85, None), height=dp(200), auto_dismiss=False)

        def do_reset(*_):
            self.cfg["counter"] = 0
            self.save()
            self.refresh()
            self.set_status("Counter reset", ok=True)
            pop.dismiss()

        yes = RoundButton(text="Yes, reset", bg=hex_("#c0392b"), on_release=do_reset)
        no = RoundButton(text="Cancel", bg=hex_("#7f8c8d"), on_release=lambda *_: pop.dismiss())
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        pop.open()

    # ---------- printer picker ----------
    def choose_printer(self, then_print=False):
        try:
            devices = BluetoothPrinter.paired_devices()
        except Exception as e:
            self.set_status(str(e), error=True)
            return

        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        pop = Popup(title="Select paired printer", content=box, size_hint=(0.92, 0.7))

        if not devices:
            box.add_widget(
                Label(
                    text="No paired devices.\nPair your printer in the phone's\nBluetooth settings first, then come back.",
                    halign="center",
                )
            )
        else:
            scroll = ScrollView()
            lst = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
            lst.bind(minimum_height=lst.setter("height"))

            def pick(name, addr):
                self.cfg["printer_name"], self.cfg["printer_addr"] = name, addr
                self.save()
                self.refresh()
                self.set_status(f"Selected {name}", ok=True)
                pop.dismiss()
                if then_print:
                    Clock.schedule_once(lambda _dt: self.new_ticket(), 0.2)

            for name, addr in devices:
                b = RoundButton(
                    text=f"{name}\n[size=12sp]{addr}[/size]",
                    markup=True,
                    halign="center",
                    size_hint_y=None,
                    height=dp(64),
                    bg=hex_("#2980b9"),
                )
                b.bind(on_release=lambda _b, n=name, a=addr: pick(n, a))
                lst.add_widget(b)
            scroll.add_widget(lst)
            box.add_widget(scroll)

        box.add_widget(
            RoundButton(text="Close", size_hint_y=None, height=dp(48), bg=hex_("#7f8c8d"), on_release=lambda *_: pop.dismiss())
        )
        pop.open()


if __name__ == "__main__":
    TokenApp().run()
