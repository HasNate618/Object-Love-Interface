const fs = require("fs");
const FILE = "./voice.json";

// List of premade voices
const voiceIds = [
  "hpp4J3VqNfWAUOO0d1Us",
  "CwhRBWXzGAHq8TQ4Fs17",
  "EXAVITQu4vr4xnSDxMaL",
  "FGY2WhTYpPnrIDTdsKH5",
  "IKne3meq5aSn9XLyUdCD",
  "JBFqnCBsd6RMkjVDRZzb",
  "N2lVS1w4EtoT3dr4eOWO",
  "SAz9YHcvj6GT2YYXdXww",
  "SOYHLrjzK2X1ezoPC6cr",
  "TX3LPaxmHKxFdv7VOQHJ"
];


function loadVoice() {
  if (!fs.existsSync(FILE)) {
    fs.writeFileSync(FILE, JSON.stringify({ voiceId: "hpp4J3VqNfWAUOO0d1Us" }, null, 2));
    return null;
  }
  return JSON.parse(fs.readFileSync(FILE)).voiceId;
}

// Function to pick a random voice
function saveRandomVoice() {
  const randomIndex = Math.floor(Math.random() * voiceIds.length);
  const voiceId = voiceIds[randomIndex];
  fs.writeFileSync("./voice.json", JSON.stringify({ voiceId }));
}
function clearVoice() {
  fs.writeFileSync(FILE, JSON.stringify({ voiceId: null }, null, 2));
}

module.exports = {
  loadVoice,
  saveRandomVoice,
  clearVoice
};
