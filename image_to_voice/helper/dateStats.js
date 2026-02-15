const STATS_FILE = "./dateStats.json";
const fs = require("fs");

function loadDateStats() {
    if (!fs.existsSync(STATS_FILE)) {
        fs.writeFileSync(STATS_FILE, JSON.stringify({
            finalInterest: 0,
            highestInterest: 0,
            lowestInterest: 10,
            averageInterest: 0,
            turnCount: 0,
            highlightMoment: "",
            followUpQuestions: 0
        }));
    }
    return JSON.parse(fs.readFileSync(STATS_FILE));
}

function saveDateStats(stats) {
    fs.writeFileSync(STATS_FILE, JSON.stringify(stats, null, 2));
}

module.exports = {
    saveDateStats,
    loadDateStats
};