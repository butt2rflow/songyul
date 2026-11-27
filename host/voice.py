#!/usr/bin/env python3
"""Voice commands: speech (int16 audio) -> text (Whisper, local) -> matching command from a YAML file.

  python3 voice.py --text "방금 거 슬라이스"            # test matching only
  python3 voice.py --wav say.wav                        # speech-to-text + matching on a recording
  python3 voice.py --list                               # show the commands file

Use from code:  vc = VoiceCommands("commands.yaml"); text = vc.transcribe(samples, 8000); cmd = vc.match(text)
cmd is None or {"action", "args", "said", "score", "text"}. Text that matches nothing is returned as
{"action": "note", "text": ...} so free speech can still be saved (or sent to Claude later).
Needs pyyaml; speech-to-text needs torch + transformers (model openai/whisper-small, downloaded once, ~1 GB).
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BUILTIN = {"label_last": "label the last swing (args: label, add_reference)", "undo_label": "remove the last label",
           "calibrate": "alignment routine: speak the guide, record args.seconds, fit the wrist hinge axis (analysis/calib.py)",
           "start": "start saving", "stop": "stop saving", "speak_last": "read the last swing's numbers aloud",
           "speak_summary": "read today's summary aloud", "speak_battery": "read the glove battery aloud",
           "set_club": "set the club for every following swing until changed (args: club); labels and references are kept per club",
           "set_swing": "set the swing type for every following swing until changed (args: swing)",
           "set_player": "set who is swinging (args: name); every following swing is saved under that player",
           "speak_club": "read the current player, club and swing type aloud",
           "note": "save free speech as a note (used when nothing matches)"}


def norm(s):
    return re.sub(r"[\s\.,!?~'\"]+", "", s.lower())


class VoiceCommands:
    def __init__(self, path=HERE / "commands.example.yaml", model="openai/whisper-small"):
        cfg = yaml.safe_load(open(path, encoding="utf-8"))
        self.min_score, self.commands, self.model_name, self._asr = cfg.get("min_score", 0.75), cfg["commands"], model, None
        self.hint = cfg.get("hint", ", ".join(p for c in self.commands for p in c["say"])) if cfg.get("use_hint", True) else ""
        self._prompt = None
        self.prefixes, self.players = cfg.get("prefixes", []), cfg.get("players", [])
        for pl in self.players:  # known players also switch with "<name> 차례" ("친구 차례")
            self.commands.append({"say": [f"{ph} 차례" for ph in pl["say"] if not ph.endswith("차례")],
                                  "action": "set_player", "args": {"name": pl["name"]}})
        for c in self.commands:
            if c["action"] not in BUILTIN:
                print(f"warning: unknown action '{c['action']}' (the app must handle it)", file=sys.stderr)

    def match(self, text):
        t = norm(text)
        if not t:
            return None
        for c in self.prefixes:  # "플레이어 게스트", "라벨 템포 좋음": the words after the prefix become the value
            for ph in c["say"]:
                i = t.find(norm(ph))
                if i >= 0 and len(t) > i + len(norm(ph)):
                    rest = self._after(text, ph)
                    if not rest or any(norm(f) == norm(rest) for c2 in self.commands for f in c2["say"]):
                        continue  # empty, or the "value" is itself a command ("선수 7번"): let the fixed phrases decide
                    if c["arg"] == "name":  # snap to a known player when close (speech-to-text often bends names)
                        rest = self._player(rest)
                    return {"action": c["action"], "args": {**c.get("args", {}), c["arg"]: rest}, "said": ph, "score": 1.0, "text": text}
        best = None
        for c in self.commands:
            for phrase in c["say"]:
                p = norm(phrase)
                if p in t:  # the phrase appears inside what was said: strong match, longer phrases win
                    score = 1.0 + len(p) / 100
                else:       # otherwise the best fuzzy match of the phrase against any same-length piece of the text
                    n = len(p)
                    score = max((difflib.SequenceMatcher(None, p, t[i:i + n]).ratio() for i in range(max(1, len(t) - n + 1))), default=0)
                if not best or score > best["score"]:
                    best = {"action": c["action"], "args": c.get("args", {}), "said": phrase, "score": round(score, 3), "text": text}
        if best and best["score"] >= self.min_score:
            # Settings can be said together ("7번 하프", "드라이버 풀스윙"): also return the other setting if its phrase
            # appears word for word in what was said (no fuzzy match here, so a stray syllable can't change a setting).
            pair = {"set_club": "set_swing", "set_swing": "set_club"}.get(best["action"])
            if pair:
                hits = [(len(norm(ph)), c) for c in self.commands if c["action"] == pair for ph in c["say"] if norm(ph) in t]
                if hits:
                    c = max(hits, key=lambda h: h[0])[1]
                    best["also"] = [{"action": c["action"], "args": c.get("args", {})}]
            return best
        return {"action": "note", "args": {}, "said": None, "score": best["score"] if best else 0, "text": text}

    @staticmethod
    def _after(text, prefix):  # the original words after the prefix (spaces kept), trailing particles trimmed
        flat, want = text.replace(" ", ""), prefix.replace(" ", "")
        j = flat.find(want)
        if j < 0:
            return ""
        k, seen = 0, 0  # map the end of the prefix in the flat text back to the original text
        while k < len(text) and seen < j + len(want):
            seen += text[k] != " "
            k += 1
        rest = text[k:].strip(" .,!?~")
        return re.sub(r"(으로|로|이요|요|입니다|이야|야)$", "", rest).strip()

    def _player(self, name):
        n, best = norm(name), (0, name)
        for pl in self.players:
            for ph in pl["say"]:
                r = difflib.SequenceMatcher(None, norm(ph), n).ratio()
                if r > best[0]:
                    best = (r, pl["name"])
        return best[1] if best[0] >= self.min_score else name

    def transcribe(self, samples, rate):
        import numpy as np
        if self._asr is None:
            import torch
            from transformers import pipeline
            dev = 0 if torch.cuda.is_available() else -1
            self._asr = pipeline("automatic-speech-recognition", model=self.model_name, device=dev)
        x = np.asarray(samples, dtype=np.float32)
        if x.dtype != np.float32 or np.abs(x).max() > 2:
            x = x / 32768.0
        # Silence gate: on a clip with no speech Whisper invents text ("구독과 좋아요 부탁드려요!", or the hint
        # repeated). Skip the first 0.2 s (the double-tap), then need one 0.1 s window above ~40/32768 rms.
        # Glove clips 2026-10-22: speech 70-240, silence 6-30.
        win = max(1, rate // 10)
        body = x[int(0.2 * rate):]
        if len(body) >= win and np.sqrt((body[:len(body) // win * win].reshape(-1, win) ** 2).mean(1)).max() < 40 / 32768:
            return ""
        if rate != 16000:  # Whisper wants 16 kHz
            x = np.interp(np.arange(0, len(x), rate / 16000), np.arange(len(x)), x).astype(np.float32)
        gk = {"language": "korean", "task": "transcribe", "max_new_tokens": 40}  # commands are short
        if self.hint:  # tell Whisper which words to expect: short commands are much easier to catch
            if self._prompt is None:
                ids = self._asr.tokenizer.get_prompt_ids(self.hint, return_tensors="pt")
                # Whisper allows 448 decoder tokens and the prompt may use at most half. The full phrase list
                # grew past that (540 tokens, 2026-10-22) and every transcription failed, so keep the first 220.
                if len(ids) > 220:
                    print(f"voice: hint is {len(ids)} tokens, using the first 220 (put key phrases first, or set 'hint' in the YAML)")
                    ids = ids[:220]
                self._prompt = ids.to(self._asr.device)
            gk["prompt_ids"] = self._prompt
        out = self._asr({"raw": x, "sampling_rate": 16000}, generate_kwargs=gk)
        txt = out["text"].strip()
        if self.hint and txt.startswith(self.hint.strip()):  # some versions echo the prompt back
            txt = txt[len(self.hint.strip()):].strip()
        # Loop guard: on faint speech Whisper can fall into the hint and repeat it ("하프, 쓰리쿼터, 하프, 풀스윙, ..."
        # x20, glove clip 2026-10-22). Any phrase 3+ times = unreliable: return nothing so the app asks again.
        parts = [w for w in re.split(r"[,.!?\s]+", txt) if w]
        if parts and max(parts.count(w) for w in set(parts)) >= 3:
            return ""
        # Echo guard: a real command names 1-3 things; 4+ phrases from the hint means Whisper read the hint back.
        if self.hint and sum(1 for h in {h.strip() for h in self.hint.split(",")} if h and h in txt) >= 4:
            return ""
        return txt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commands", default=str(HERE / "commands.example.yaml"))
    ap.add_argument("--text"); ap.add_argument("--wav"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--model", default="openai/whisper-small")
    a = ap.parse_args()
    vc = VoiceCommands(a.commands, a.model)
    if a.list:
        for c in vc.commands:
            print(f"{', '.join(c['say']):30} -> {c['action']} {c.get('args', '')}")
        return
    if a.wav:
        import numpy as np, wave
        w = wave.open(a.wav); x = np.frombuffer(w.readframes(w.getnframes()), "<i2")
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(1)
        a.text = vc.transcribe(x, w.getframerate()); print("heard:", a.text)
    if a.text is not None:
        print(vc.match(a.text))


if __name__ == "__main__":
    main()
