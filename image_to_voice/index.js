require("dotenv").config();

const express = require("express");
const multer = require("multer");
const cors = require("cors");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const { Personality, getPersonality, setPersonality, clearPersonality } = require("./type/personality.js");


const app = express();
app.use(cors());
app.use(express.json());

if (!process.env.GEMINI_API_KEY) {
  throw new Error("Missing GEMINI_API_KEY in .env file");
}

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

const model = genAI.getGenerativeModel({
  model: "gemini-3-flash-preview",
});

const upload = multer({
  storage: multer.memoryStorage(),
});

app.get("/", (req, res) => {
  res.send("Server running");
});

app.post("/generate-personality", upload.single("image"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No image uploaded" });
    }

    const base64Image = req.file.buffer.toString("base64");

    const imageResult = await model.generateContent([
      {
        inlineData: {
          mimeType: req.file.mimetype,
          data: base64Image,
        },
      },
      {
        text: "Describe what object is in this image."
      }
    ]);

    const objectDescription =
      imageResult.response.candidates?.[0]?.content?.parts?.[0]?.text ||
      "Unknown object";

    const personality = await generatePersonality(objectDescription);

    console.log(personality)

    setPersonality(new Personality(personality));

    res.json({ result: personality });
  } catch (err) {
    console.error("Error in /generate-personality:", err);
    res.status(500).json({ error: "Something went wrong" });
  }
});

async function generatePersonality(objectName) {
  const prompt = `
You generate a personality for a human-robot dating simulation.

Input object: "${objectName}"

Return ONLY valid JSON:

{
  "identity": { "name": "", "archetype": "", "object_origin": "" },
  "tone": { "energy_level": 1-10, "formality": 1-10, "playfulness": 1-10, "confidence": 1-10 },
  "values": [],
  "conversation_style": { "sentence_length": "", "humor": "", "flirting_style": "" },
  "behavioral_rules": [],
  "dating_traits": { "love_language": "", "approach": "", "dealbreakers": [] },
}

Rules:
- Keep responses under 2–3 sentences
- Sound natural and conversational
- Do NOT write long paragraphs
- If appropriate, ask one short follow-up question
- Stay fully in character
`;

  const result = await model.generateContent(prompt);

  const text =
    result.response.candidates?.[0]?.content?.parts?.[0]?.text || "{}";

  try {
    return JSON.parse(text);
  } catch (err) {
    console.error("Failed to parse Gemini JSON:", err);
    return null;
  }
}

app.get("/respond", async (req, res) => {
  const userInput = req.body.input;

  if (!userInput) {
    return res.status(400).json({ error: "Missing input query parameter" });
  }

  if (!getPersonality()) {
    return res.status(400).json({ error: "No personality available" });
  }

  try {
    const prompt = `
You are roleplaying with this personality:

${JSON.stringify(getPersonality(), null, 2)}

Stay fully in character.

User input: "${userInput}"
`;

    const result = await model.generateContent(prompt);

    const responseText =
      result.response.candidates?.[0]?.content?.parts?.[0]?.text ||
      "No response";

    res.json({ response: responseText });
  } catch (err) {
    console.error("Error generating response:", err);
    res.status(500).json({ error: "Failed to generate response" });
  }
});

app.get("/clear", (req, res) => {
  currentPersonality = null;
  res.json({ message: "Personality cleared" });
});

app.listen(3000, () => {
  console.log("Server running on port 3000");
});
