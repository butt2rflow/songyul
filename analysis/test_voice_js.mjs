// Checks the phone's voice matcher (phone/voice.js + commands.json) against the PC's voice.py on the same sentences.
//   node test_voice_js.mjs   (needs python3 with pyyaml for voice.py)
import { readFileSync } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { VoiceCommands } from "../phone/voice.js";
const host = fileURLToPath(new URL("../host/", import.meta.url));
const vc = new VoiceCommands(JSON.parse(readFileSync(new URL("../phone/commands.json", import.meta.url), "utf8")));
const SAY = ["칠번 하프", "7번 하프", "드라이버 풀스윙", "굿샷", "나이스 샷", "뒤땅", "방금 거 슬라이스", "플레이어 게스트", "선수 게스트요",
  "라벨 템포 좋음", "친구 차례", "내 차례", "피칭 웨지", "샌드웨지 벙커샷", "56도", "삼번 우드", "유틸리티", "기록 시작", "그만",
  "방금 거 어때", "배터리", "취소", "정렬 시작", "무슨 채야", "오늘 요약", "탑볼", "얇게 맞았어", "빈 스윙", "칠 번", "세븐 아이언",
  "하프스윙", "쓰리쿼터", "펀치 샷", "오늘 날씨 좋다", "음", "구번 아이언 칩샷", "훅이네", "슬라이스 났어", "선수 친구", "하이브리드 하프",
  "드라이브", "슬라이즈", "피칭웨지요", "칠번 하푸", "구샷", "뒤땅이요", "뒷땅", "뒷땅이야", "뒤탕", "땅 먼저 쳤어", "탑 볼", "벙커샤", "쓰리 쿼터", "로브웨지", "배러리", "기록 시자", "플레이어 친구", "라벨 슬라이스", "사번 아이어"];
const { stdout } = await promisify(execFile)("python3", ["-c", `
import json, sys
sys.path.insert(0, ${JSON.stringify(host)})
from voice import VoiceCommands
vc = VoiceCommands()
print(json.dumps([vc.match(s) for s in json.loads(sys.argv[1])], ensure_ascii=False))
`, JSON.stringify(SAY)], { encoding: "utf8" });
const py = JSON.parse(stdout);
let same = 0;
const key = (m) => m ? JSON.stringify([m.action, m.args, (m.also || []).map((a) => [a.action, a.args])]) : "null";
SAY.forEach((s, i) => {
  const j = vc.match(s), p = py[i], ok = key(j) === key(p);
  same += ok;
  console.log(`${ok ? "ok  " : "DIFF"} ${s.padEnd(14)} js ${key(j)} ${j ? j.score : ""}${ok ? "" : `\n      py ${key(p)} ${p ? p.score : ""}`}`);
});
console.log(`${same}/${SAY.length} identical`);
if (same !== SAY.length) process.exitCode = 1;
