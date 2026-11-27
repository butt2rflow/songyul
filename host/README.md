# Host tools

Run from the repository root with `python3 -m pip install -r host/requirements.txt` in a virtual environment.

- `stream.py` records a USB sketch or a BLE-to-USB receiver. Use `--list` for ports and `--selftest` to check the decoder without hardware.
- `voice.py` loads `commands.example.yaml`. Try `python3 host/voice.py --text "칠번 하프"`. Transcribing a local mono 16-bit WAV with `--wav` also requires PyTorch and Transformers. The default Whisper model downloads on first use. Use `--commands` for a local YAML file.
- `commands_to_json.py` regenerates the phone's `commands.json` from the YAML. Run `python3 host/commands_to_json.py` after editing the example.
- `ble_glove_check.py` and `ble_glove_test.py` need Bleak and use the computer's own Bluetooth adapter. Run them with `--help` for available options.
- `hex_to_uf2.py` converts a locally compiled Intel HEX image for the XIAO bootloader.

Check recordings for personal information before sharing them.

Songyul host code uses [PolyForm Noncommercial 1.0.0](../LICENSE). See [THIRD_PARTY.md](../THIRD_PARTY.md) for external dependencies.
