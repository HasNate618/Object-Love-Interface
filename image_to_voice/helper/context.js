const CONTEXT_FILE = "./dateContext.json";
const fs = require("fs");

// Load context from file (or create a fresh one if missing)
function loadContext() {
    if (!fs.existsSync(CONTEXT_FILE)) {
        fs.writeFileSync(
            CONTEXT_FILE,
            JSON.stringify({
                turns: [] // Each turn will have { user, ai, interest }
            }, null, 2)
        );
    }

    return JSON.parse(fs.readFileSync(CONTEXT_FILE));
}

// Save context back to file
function saveContext(context) {
    fs.writeFileSync(CONTEXT_FILE, JSON.stringify(context, null, 2));
}

// Add a new turn to the context
function addTurn(userMessage, aiMessage, interest) {
    const context = loadContext();
    context.turns.push({
        user: userMessage,
        ai: aiMessage,
        interest: interest // numeric 0-10
    });
    saveContext(context);
}

// Clear context (optional, e.g., when starting a new date)
function clearContext() {
    fs.writeFileSync(
        CONTEXT_FILE,
        JSON.stringify({ turns: [] }, null, 2)
    );
}

// Export functions
module.exports = {
    loadContext,
    saveContext,
    addTurn,
    clearContext
};
