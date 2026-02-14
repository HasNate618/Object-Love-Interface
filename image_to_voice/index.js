require("dotenv").config();

const express = require("express");
const WebSocket = require("ws");
const multer = require("multer");
const cors = require("cors");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const { Personality, getPersonality, setPersonality, clearPersonality } = require("./type/personality.js");
const fs = require("fs");
const axios = require('axios')
const { ElevenLabsClient, play, stream } = require('@elevenlabs/elevenlabs-js');
const mic = require("mic");



const app = express();
app.use(cors());
app.use(express.json());

if (!process.env.GEMINI_API_KEY) {
  throw new Error("Missing GEMINI_API_KEY in .env file");
}

const elevenlabs = new ElevenLabsClient({
  apiKey: process.env.ELEVENLABS_API_KEY, // Defaults to process.env.ELEVENLABS_API_KEY
});


const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

const model = genAI.getGenerativeModel({
  model: "gemini-2.0-flash",
  generationConfig: {
    maxOutputTokens: 350,
  }
});

const upload = multer({
  storage: multer.memoryStorage(),
});

/*
const ws = new WebSocket("wss://api.elevenlabs.io/v1/speech-to-text/realtime", {
  headers: {
    "xi-api-key": process.env.ELEVENLABS_API_KEY,
  },
});

ws.on("open", () => {
  console.log("Connected to ElevenLabs Realtime STT");

  // ---- Start microphone capture ----
  const micInstance = mic({
    rate: "16000",
    channels: "1",
    bitwidth: "16",
    encoding: "signed-integer",
    endian: "little",
    device: "default",
    fileType: "wav",
    exitOnSilence: 0,
    // force using FFmpeg as backend
    debug: false
  });
  const micInputStream = micInstance.getAudioStream();
  micInputStream.on("data", (chunk) => {
    const base64Chunk = chunk.toString("base64");
    ws.send(JSON.stringify({
      message_type: "input_audio_chunk",
      audio_base_64: base64Chunk,
      commit: false
    }));
  });

  micInstance.start();
});

// ---- Handle transcription ----
ws.on("message", async (data) => {
  const msg = JSON.parse(data);

  if (msg.message_type === "partial_transcript") {
    process.stdout.write(msg.text + "\r");
  }

  if (msg.message_type === "committed_transcript") {
    console.log("\nFinal Transcript:", msg.text);

    // ---- Send to Gemini AI ----
    const responseText = await getResponse(msg.text);

    console.log("AI Response:", responseText);
  }
});
*/

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

    fs.writeFileSync("personality.json", JSON.stringify(personality));
    fs.writeFileSync("interest.json", JSON.stringify({ interest: 5 }))


    const starterPrompt = `
      You are roleplaying with this personality:

      ${JSON.stringify(personality, null, 2)}

      Write a very short, friendly conversation starter to begin talking with the user.
      Rules:
        - Keep responses under 2 sentences
        - No emoji output
        - Sound natural and conversational
        - Do NOT write long paragraphs
        - Stay fully in character
      `;

    const starterResult = await model.generateContent(starterPrompt);
    const starterText = starterResult.response.candidates?.[0]?.content?.parts?.[0]?.text || "Hello!";
    setRandomVoice();
    await textToSpeech(starterText);

    res.json({
      personality,
      starter: starterText
    });

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
  "negative_traits": []
}

Rules:
- Keep responses under 2-3 sentences
- No emoji output
- Sound natural and conversational
- Do NOT write long paragraphs
- If appropriate, ask one short follow-up question
- Stay fully in character
`;

  const result = await model.generateContent(prompt);

  let text =
    result.response.candidates?.[0]?.content?.parts?.[0]?.text || "{}";

  // Strip Markdown code fences if present
  text = text.trim();

  if (text.startsWith("```")) {
    text = text
      .replace(/^```(?:json)?/i, "")
      .replace(/```$/, "")
      .trim();
  }

  try {
    return JSON.parse(text);
  } catch (err) {
    console.error("Failed to parse Gemini JSON:", text);
    throw err;
  }
}


async function getResponse(input) {

  if (!input) {
    return res.status(400).json({ error: "Missing input query parameter" });
  }

  try {
    if (!fs.existsSync("personality.json")) {
      return res.status(400).json({ error: "No personality available" });
    }

    personality = JSON.parse(fs.readFileSync("personality.json"));
  } catch (err) {
    return res.status(500).json({ error: "Failed to load personality" });
  }

  try {
    const prompt = `
You are roleplaying with this personality:

${JSON.stringify(personality, null, 2)}

Stay fully in character.

User input: "${input}"
`;

    const result = await model.generateContent(prompt);

    const responseText =
      result.response.candidates?.[0]?.content?.parts?.[0]?.text ||
      "No response";

    res.json({ response: responseText });

    textToSpeech(responseText);
  } catch (err) {
    console.error("Error generating response:", err);
    res.status(500).json({ error: "Failed to generate response" });
  }
}

app.post("/respond", async (req, res) => {
  const userInput = req.body.input;

  if (!userInput) {
    return res.status(400).json({ error: "Missing input query parameter" });
  }

  try {
    if (!fs.existsSync("personality.json")) {
      return res.status(400).json({ error: "No personality available" });
    }

    if(!fs.existsSync("interest.json")) {
      return res.status(400).json({ error: "No interest available" });
    }

    personality = JSON.parse(fs.readFileSync("personality.json"));
    interest = JSON.parse(fs.readFileSync("interest.json")).ineterst;
  } catch (err) {
    return res.status(500).json({ error: "Failed to load personality" });
  }

  try {
    const prompt = `
      You are roleplaying with this personality:

      ${JSON.stringify(personality, null, 2)}

      Current interest level (0-10): ${interest}

      User input: "${userInput}"

      Stay fully in character.

      TASK 1 — Update Interest:
      Evaluate the user's input using these rules:

      - If input aligns with your values → +0.5
      - If input matches your flirting_style → +0.5
      - If input shows curiosity or emotional awareness → +0.3
      - If input violates a dealbreaker → -0.5
      - If input triggers a negative trait → -0.3
      - Otherwise → 0

      Adjust the current interest level slightly based on the above.
      Clamp the final value between 0 and 10.

      TASK 2 — Generate Response:
      Generate a short reply (1-2 sentences max) that reflects:
      - Your personality
      - Your flirting_style
      - Your updated interest level

      Interest behavior guide:
      0-2 → distant, guarded
      3-5 → polite, neutral
      6-8 → warm, engaged
      9-10 → highly engaged, flirtatious

      Return ONLY valid JSON in this exact format:

      {
        "interest": number,
        "response": string
      }
    `;


    const result = await model.generateContent(prompt);

    const rawText =
      result.response.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || "{}";

    // Remove markdown code blocks if present
    const cleanedText = rawText
      .replace(/```json/g, "")
      .replace(/```/g, "")
      .trim();

    let parsed;

    try {
      parsed = JSON.parse(cleanedText);
    } catch (err) {
      console.error("Failed to parse Gemini JSON:", rawText);
      parsed = {
        interest: interest,
        response: "Sorry, I got distracted for a second."
      };
    }


    // Update interest safely
    interest = Math.max(0, Math.min(10, parsed.interest));

    // Send clean response
    res.json({
      response: parsed.response,
      interest: interest
    });

    // TTS only speaks the response text
    textToSpeech(parsed.response);
    fs.writeFileSync("interest.json", JSON.stringify({ interest }));

  } catch (err) {
    console.error("Error generating response:", err);
    res.status(500).json({ error: "Failed to generate response" });
  }
});


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

// Function to pick a random voice
function setRandomVoice() {
  const randomIndex = Math.floor(Math.random() * voiceIds.length);
  const voiceId = voiceIds[randomIndex];
  fs.writeFileSync("./voice.json", JSON.stringify({ voiceId }));
}

async function streamToBuffer(stream) {
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}


// Serve the audio file
app.use("/tmp", express.static("./tmp"));

async function playOnRobot(ttsUrl) {
  try {
    await axios.post("http://10.216.64.147:8082/play", {
      url: ttsUrl,
      format: "mp3",
    });
    console.log("TTS playing on robot!");
  } catch (err) {
    console.error("Failed to play on robot:", err);
  }
}

app.post("/tts", async (req, res) => {
  const text = req.body.text;
  if (!text) return res.status(400).json({ error: "Missing text" });

  try {

    const voiceId = JSON.parse(fs.readFileSync("voice.json")).voiceId;
    const audioStream = await elevenlabs.textToSpeech.convert(
      voiceId,
      {
        text,
        modelId: "eleven_multilingual_v2",
        outputFormat: "mp3_44100_128",
      }
    );

    const audioBuffer = await streamToBuffer(audioStream);

    const tempFile = "./tmp/audio.mp3";
    fs.writeFileSync(tempFile, audioBuffer);

    // playOnRobot(`http://10.216.64.252:3000/tmp/audio.mp3`)
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "TTS failed" });
  }
});

async function textToSpeech(text) {
  try {
    console.log("Starting:", text)
    const voiceId = JSON.parse(fs.readFileSync("voice.json")).voiceId;
    const audioStream = await elevenlabs.textToSpeech.convert(
      voiceId,
      {
        text,
        modelId: "eleven_multilingual_v2",
        outputFormat: "mp3_44100_128",
      }
    );

    const audioBuffer = await streamToBuffer(audioStream);

    const tempFile = "./tmp/audio.mp3";
    fs.writeFileSync(tempFile, audioBuffer);

    console.log("PLay")

    playOnRobot(`http://${process.env.LOCAL_IP}/tmp/audio.mp3`)
  } catch (error) {
    console.error("TTS Error:", error.response?.data || error.message);
  }
}


app.get("/clear", (req, res) => {
  clearPersonality(); // Modifty for proper removal
  res.json({ message: "Personality cleared" });
});

// Write return-summary which summarizes

app.listen(3000, () => {
  console.log("Server running on port 3000");
});
