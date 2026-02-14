// Define the Personality structure as a class
class Personality {
  constructor({
    identity = { name: "", archetype: "", object_origin: "" },
    tone = { energy_level: 0, formality: 0, playfulness: 0, confidence: 0 },
    values = [],
    conversation_style = { sentence_length: "", emoji_usage: "", humor: "", flirting_style: "" },
    behavioral_rules = [],
    dating_traits = { love_language: "", approach: "", dealbreakers: [] },
    catchphrases = []
  } = {}) {
    this.identity = identity;
    this.tone = tone;
    this.values = values;
    this.conversation_style = conversation_style;
    this.behavioral_rules = behavioral_rules;
    this.dating_traits = dating_traits;
    this.catchphrases = catchphrases;
  }
}

// In-memory storage for the current personality
let currentPersonality = null;

// Functions to manage the personality
function setPersonality(personality) {
  if (!(personality instanceof Personality)) {
    throw new Error("Must pass a Personality instance");
  }
  currentPersonality = personality;
}

function getPersonality() {
  return currentPersonality;
}

function clearPersonality() {
  currentPersonality = null;
}

// Export the class and functions
module.exports = {
  Personality,
  setPersonality,
  getPersonality,
  clearPersonality
};
