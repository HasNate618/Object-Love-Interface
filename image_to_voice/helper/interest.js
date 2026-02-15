const fs = require("fs");
const FILE = "./interest.json";

function loadInterest() {
  if (!fs.existsSync(FILE)) {
    fs.writeFileSync(FILE, JSON.stringify({ interest: 5 }, null, 2)); // default 5
  }
  return JSON.parse(fs.readFileSync(FILE)).interest;
}

function saveInterest(value) {
  fs.writeFileSync(FILE, JSON.stringify({ interest: value }, null, 2));
}

function clearInterest() {
  fs.writeFileSync(FILE, JSON.stringify({ interest: 5 }, null, 2)); // reset to default
}

module.exports = {
  loadInterest,
  saveInterest,
  clearInterest
};
