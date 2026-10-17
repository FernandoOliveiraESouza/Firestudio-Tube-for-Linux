"""Backend for the PreSonus FireStudio Tube's on-board DSP (TCAT DICE II).

snd-dice-ctl-service (from snd-firewire-ctl-services) exposes the router and
mixer of the interface as ALSA control elements. This module reads and writes
those elements through amixer, the same way Universal Control does on Windows
through the PreSonus driver.

Layout of the hardware:
  * 16 analog inputs (Mic 1-8, Line 9-14, Tube 15-16)
  * 8 DAW playback channels from the computer (Stream-1..8)
  * a mixer with 18 inputs (any of the sources above) and 16 outputs
  * 8 physical outputs (Main L/R, Out 3-6, Phones L/R), each fed by any
    analog input, DAW channel or mixer output.
Mixer gains are 2:14 fixed point: 16384 is unity (0 dB).
"""

import json
import math
import os
import re
import subprocess
import time
import wave

UNITY = 16384
GAIN_MAX = 65535
# Meters are linear peak values: a -20 dBFS sine reads 409.
METER_FULL_SCALE = 4095

INPUT_NAMES = [f"Mic {n}" for n in range(1, 9)] + \
    [f"Line {n}" for n in range(9, 15)] + ["Tube 15", "Tube 16"]
OUTPUT_NAMES = ["Main L", "Main R", "Out 3", "Out 4", "Out 5", "Out 6",
                "Phones L", "Phones R"]
OUTPUT_PAIRS = [("Main", 0), ("Out 3-4", 2), ("Out 5-6", 4), ("Phones", 6)]
MIXER_INPUTS = 18
MIXER_OUTPUTS = 16


def find_card():
    """Card number of the FireStudio Tube, or None when it is not connected."""
    try:
        with open("/proc/asound/cards") as f:
            for line in f:
                m = re.match(r"\s*(\d+)\s+\[.*\]:\s+DICE - FireStudio Tube", line)
                if m:
                    return int(m.group(1))
    except OSError:
        pass
    return None


def source_label(item):
    """Human label for a router item name such as 'Analog-A-3' or 'Stream-7'."""
    m = re.fullmatch(r"Analog-A-(\d+)", item)
    if m:
        n = int(m.group(1))
        return INPUT_NAMES[n - 1] if 1 <= n <= len(INPUT_NAMES) else item
    m = re.fullmatch(r"Stream-(\d+)", item)
    if m:
        return f"DAW {m.group(1)}"
    m = re.fullmatch(r"Mixer-(\d+)", item)
    if m:
        return f"Mix {m.group(1)}"
    return "Nenhum" if item == "None" else item


def gain_to_db(value):
    return -math.inf if value <= 0 else 20 * math.log10(value / UNITY)


def db_to_gain(db):
    if db == -math.inf or db <= -60:
        return 0
    return max(0, min(GAIN_MAX, round(UNITY * 10 ** (db / 20))))


def stereo_to_level_pan(left, right):
    """Constant-power pan (what Universal Control uses: centre = -3 dB per side).

    Returns (gain, pan) with pan in -1 (left) .. +1 (right).
    """
    level = math.hypot(left, right)
    if level == 0:
        return 0, 0.0
    theta = math.atan2(right, left)  # 0 = hard left, pi/2 = hard right
    return level, theta / (math.pi / 4) - 1


def level_pan_to_stereo(level, pan):
    theta = (pan + 1) * math.pi / 4
    clamp = lambda v: max(0, min(GAIN_MAX, round(v)))
    return clamp(level * math.cos(theta)), clamp(level * math.sin(theta))


def meter_to_db(value):
    return -math.inf if value <= 0 else 20 * math.log10(value / METER_FULL_SCALE)


class Control:
    def __init__(self, numid, name, index):
        self.numid = numid
        self.name = name
        self.index = index
        self.type = None
        self.items = []
        self.values = []


class Tube:
    def __init__(self, card=None):
        self.card = find_card() if card is None else card
        if self.card is None:
            raise RuntimeError("FireStudio Tube não encontrada (está ligada?)")
        self.controls = {}
        self.refresh()
        if ("output-source", 0) not in self.controls:
            raise RuntimeError(
                "O serviço snd-dice-ctl-service não está rodando para a placa "
                f"{self.card} (systemctl --user start firestudio-tube-ctl)")

    def _amixer(self, *args):
        return subprocess.run(["amixer", "-c", str(self.card), *args],
                              capture_output=True, text=True, check=True).stdout

    def refresh(self):
        self.controls = {}
        current = None
        for line in self._amixer("contents").splitlines():
            m = re.match(r"numid=(\d+),iface=\w+,name='([^']*)'(?:,index=(\d+))?", line)
            if m:
                current = Control(int(m.group(1)), m.group(2), int(m.group(3) or 0))
                self.controls[(current.name, current.index)] = current
                continue
            if current is None:
                continue
            line = line.strip()
            if line.startswith("; type="):
                current.type = line[len("; type="):].split(",")[0]
            elif m := re.match(r"; Item #\d+ '(.*)'", line):
                current.items.append(m.group(1))
            elif line.startswith(": values="):
                current.values = line[len(": values="):].split(",")

    def _ctl(self, name, index=0):
        return self.controls[(name, index)]

    def _ints(self, name, index=0):
        return [int(v) for v in self._ctl(name, index).values]

    def _enum_names(self, name):
        ctl = self._ctl(name)
        return [ctl.items[int(v)] for v in ctl.values]

    def _set(self, name, index, values):
        ctl = self._ctl(name, index)
        self._amixer("-q", "cset", f"numid={ctl.numid}", ",".join(str(v) for v in values))
        ctl.values = [str(v) for v in values]

    def _set_enum(self, name, item_names):
        ctl = self._ctl(name)
        self._set(name, 0, [ctl.items.index(n) for n in item_names])

    # Router ---------------------------------------------------------------
    def output_items(self):
        return list(self._ctl("output-source").items)

    def output_sources(self):
        return self._enum_names("output-source")

    def set_output_sources(self, items):
        self._set_enum("output-source", items)

    def mixer_items(self):
        return list(self._ctl("mixer-source").items)

    def mixer_sources(self):
        return self._enum_names("mixer-source")

    def set_mixer_sources(self, items):
        self._set_enum("mixer-source", items)

    # Mixer ------------------------------------------------------------------
    def mixer_gains(self, mixer_out):
        """Gains of the 18 mixer inputs into mixer output `mixer_out` (0-based)."""
        return self._ints("mixer-source-gain", mixer_out)

    def set_mixer_gains(self, mixer_out, gains):
        self._set("mixer-source-gain", mixer_out, gains)

    # Clock ------------------------------------------------------------------
    def sample_rate(self):
        return self._enum_names("clock-rate")[0]

    def locked(self):
        return self._ctl("locked-clock-source").values[0] == "on"

    # Meters -----------------------------------------------------------------
    def enable_metering(self):
        # The meters only start updating on an off -> on transition, even when
        # the element already reads "on" (e.g. after the service restarted).
        if ("metering", 0) in self.controls:
            self._set("metering", 0, ["off"])
            self._set("metering", 0, ["on"])

    def read_saturation(self):
        out = self._amixer("cget", f"numid={self._ctl('mixer-out-saturation').numid}")
        return [v == "on" for v in out.strip().splitlines()[-1].split("=", 1)[1].split(",")]

    def read_meters(self):
        """(mixer input meters [18], output meters [8]) as raw 0..4095 values."""
        def cget(name):
            out = self._amixer("cget", f"numid={self._ctl(name).numid}")
            values = out.strip().splitlines()[-1].split("=", 1)[1]
            return [int(v) for v in values.split(",")]
        return cget("mixer-source-meter"), cget("output-source-meter")

    # Presets ----------------------------------------------------------------
    def snapshot(self):
        return {
            "mixer_sources": self.mixer_sources(),
            "mixer_gains": [self.mixer_gains(i) for i in range(MIXER_OUTPUTS)],
            "outputs": self.output_sources(),
        }

    def apply(self, preset):
        self.set_mixer_sources(preset["mixer_sources"])
        for i, gains in enumerate(preset["mixer_gains"]):
            self.set_mixer_gains(i, gains)
        self.set_output_sources(preset["outputs"])


# Sample rate and buffer size ----------------------------------------------------
# On Linux PipeWire opens the interface, so it decides both: the graph rate and
# the quantum (buffer size, in samples). Universal Control's choices:
SAMPLE_RATES = [44100, 48000, 88200, 96000]
BUFFER_SIZES = [32, 64, 128, 256, 512, 1024, 2048, 4096]
CLOCK_CONF = os.path.expanduser("~/.config/pipewire/pipewire.conf.d/firestudio-tube-clock.conf")


def pw_settings():
    """Current PipeWire clock settings, e.g. {'clock.rate': '48000', ...}."""
    out = subprocess.run(["pw-metadata", "-n", "settings", "0"],
                         capture_output=True, text=True).stdout
    return dict(re.findall(r"key:'([^']+)' value:'([^']*)'", out))


def current_clock():
    """(sample rate, buffer size) the graph is using now."""
    s = pw_settings()
    rate = int(s.get("clock.force-rate", "0") or 0) or int(s.get("clock.rate", "48000"))
    quantum = int(s.get("clock.force-quantum", "0") or 0) or int(s.get("clock.quantum", "1024"))
    return rate, quantum


def set_clock(rate, quantum):
    """Applies rate/buffer now and writes them for the next boot."""
    subprocess.run(["pw-metadata", "-n", "settings", "0", "clock.force-rate", str(rate)],
                   capture_output=True, check=True)
    subprocess.run(["pw-metadata", "-n", "settings", "0", "clock.force-quantum", str(quantum)],
                   capture_output=True, check=True)
    os.makedirs(os.path.dirname(CLOCK_CONF), exist_ok=True)
    with open(CLOCK_CONF, "w") as f:
        f.write("# Written by firestudio-control: sample rate and buffer size of the\n"
                "# FireStudio Tube (the whole PipeWire graph runs at this rate).\n"
                "context.properties = {\n"
                f"    default.clock.rate = {rate}\n"
                f"    default.clock.allowed-rates = [ {rate} ]\n"
                f"    default.clock.quantum = {quantum}\n"
                f"    default.clock.min-quantum = {quantum}\n"
                f"    default.clock.max-quantum = {quantum}\n"
                "}\n")


def wake_stream(seconds=0.6):
    """Plays a moment of silence so PipeWire opens the device at the new rate."""
    rate = current_clock()[0]
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "firestudio-silence.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0" * 4 * int(rate * seconds))
    subprocess.run(["paplay", "--device=firestudio_tube", path], capture_output=True)


def restart_service(timeout=8.0):
    """Restarts snd-dice-ctl-service, which stores the configuration to flash when
    it stops and re-reads the device when it starts. Returns a fresh Tube."""
    subprocess.run(["systemctl", "--user", "restart", "firestudio-tube-ctl"],
                   capture_output=True, check=True)
    deadline = time.monotonic() + timeout
    while True:
        time.sleep(0.5)
        try:
            return Tube()
        except (RuntimeError, subprocess.CalledProcessError, KeyError):
            if time.monotonic() > deadline:
                raise


def apply_and_store(config, attempts=3):
    """Applies a device configuration, stores it to flash and checks the device
    really holds it (re-reading after a service restart). Right after a rate
    change the DICE reloads its flash and can overwrite what was just written."""
    for _ in range(attempts):
        Tube().apply(config)
        t = restart_service()
        current = t.snapshot()
        if all(current[k] == config[k] for k in ("mixer_sources", "mixer_gains", "outputs")):
            return t
        time.sleep(1.0)
    raise RuntimeError("a placa não manteve a configuração")


def load_preset(path):
    with open(path) as f:
        return json.load(f)


def save_preset(path, preset):
    with open(path, "w") as f:
        json.dump(preset, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    import sys
    tube = Tube()
    if len(sys.argv) == 3 and sys.argv[1] == "apply":
        tube.apply(load_preset(sys.argv[2]))
        print(f"Preset aplicado: {sys.argv[2]}")
    elif len(sys.argv) == 3 and sys.argv[1] == "save":
        save_preset(sys.argv[2], tube.snapshot())
        print(f"Estado atual salvo em {sys.argv[2]}")
    else:
        print(f"FireStudio Tube na placa {tube.card}, {tube.sample_rate()} Hz")
        for name, src in zip(OUTPUT_NAMES, tube.output_sources()):
            print(f"  {name:9} <- {source_label(src)}")
        print("Uso: tube.py [apply|save] preset.json")
