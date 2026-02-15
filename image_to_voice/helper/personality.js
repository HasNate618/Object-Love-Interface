const fs = require("fs");
const FILE = "./personality.json";

function loadPersonality() {
  if (!fs.existsSync(FILE)) {
    fs.writeFileSync(FILE, JSON.stringify(null, null, 2));
    return null;
  }
  return JSON.parse(fs.readFileSync(FILE));
}

function savePersonality(personality) {
  fs.writeFileSync(FILE, JSON.stringify(personality, null, 2));
}

function clearPersonality() {
  fs.writeFileSync(FILE, JSON.stringify(null, null, 2));
}

module.exports = {
  loadPersonality,
  savePersonality,
  clearPersonality
};
