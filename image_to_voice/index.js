require("dotenv").config();

const express = require("express");
const WebSocket = require("ws");
const multer = require("multer");
const cors = require("cors");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const fs = require("fs");
const os = require("os");
const axios = require('axios')
const { ElevenLabsClient, play, stream } = require('@elevenlabs/elevenlabs-js');


const { loadDateStats, saveDateStats } = require("./helper/dateStats.js");
const { loadPersonality, savePersonality, clearPersonality } = require("./helper/personality.js");
const { loadInterest, saveInterest, clearInterest } = require("./helper/interest.js");
const { loadVoice, saveRandomVoice, clearVoice } = require("./helper/voice.js");
const { addTurn, loadContext, clearContext } = require("./helper/context.js")
const mic = require("mic");

// ---------------------------------------------------------------------------
// Auto-detect the server's LAN IP so the M5 speaker can reach audio URLs.
// Falls back to 127.0.0.1 if no suitable interface is found.
// ---------------------------------------------------------------------------
function getLocalIP() {
  const nets = os.networkInterfaces();
  for (const name of Object.keys(nets)) {
    for (const net of nets[name]) {
      // Skip loopback & non-IPv4
      if (net.family === "IPv4" && !net.internal) {
        return net.address;
      }
    }
  }
  return "127.0.0.1";
}

const LOCAL_IP = process.env.HOST_IP || getLocalIP();



const app = express();
app.use(cors());
app.use(express.json());

const SERVER_PORT = process.env.PORT || 3000;
const ROBOT_PLAY_URL = process.env.M5CORE2_URL;            // e.g. http://<m5_ip>:8082/play
const AUDIO_HOST_URL = process.env.AUDIO_HOST_URL || `http://${LOCAL_IP}:${SERVER_PORT}`;
const DISABLE_ROBOT_TTS = process.env.DISABLE_ROBOT_TTS === "1";

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
    maxOutputTokens: 1500,
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

    savePersonality(personality);
    saveInterest(5);
    clearContext();


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
    saveRandomVoice();
    // await textToSpeech(starterText);

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
    return safeParseJson(text);
  } catch (err) {
    console.error("Failed to parse Gemini JSON:", text);
    throw err;
  }
}

function safeParseJson(raw) {
  // Extract the first JSON object block if extra text leaked in
  let text = raw.trim();
  const firstBrace = text.indexOf("{");
  const lastBrace = text.lastIndexOf("}");
  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    text = text.slice(firstBrace, lastBrace + 1);
  }

  // Remove JS-style comments and trailing commas
  text = text
    .replace(/\/\/.*$/gm, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/,\s*([}\]])/g, "$1");

  return JSON.parse(text);
}

/*
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
*/

app.post("/respond", async (req, res) => {
  const userInput = req.body.input;

  if (!userInput) {
    return res.status(400).json({ error: "Missing input query parameter" });
  }

  try {
    personality = loadPersonality();
    interest = loadInterest();
    context = loadContext();
    console.log(context);

    const lastTwoTurns = context.turns.slice(-2);
    formattedContext = lastTwoTurns
      .map(turn =>
        `User: ${turn.user}\nAI: ${turn.ai}`
      )
      .join("\n\n");

  } catch (err) {
    return res.status(500).json({ error: "Failed to load personality" });
  }

  try {
    const prompt = `
      You are roleplaying with this personality at a dinner date!:

      ${personality}

      !Recent conversation (most recent last)!:
      
      ${formattedContext}

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

      RULE:
      - No emoji output
      - Sound natural and conversational
      - Do NOT write long paragraphs
      - Stay fully in character
      - You must always have a specific preference based on your physical form
      - You must end with a question only when appropriate

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
        interest,
        response: "Sorry, I got distracted for a second."
      };
    }


    // Update interest safely
    interest = Math.max(0, Math.min(10, parsed.interest));

    const stats = loadDateStats();

    stats.turnCount += 1;
    stats.finalInterest = interest;
    stats.highestInterest = Math.max(stats.highestInterest, interest);
    stats.lowestInterest = Math.min(stats.lowestInterest, interest);
    stats.averageInterest = Math.round((((stats.averageInterest * (stats.turnCount - 1)) + interest) / stats.turnCount) * 10) / 10;
    if (interest === stats.highestInterest) {
      stats.highlightMoment = userInput;
    }

    if (parsed.response.includes("?")) stats.followUpQuestions += 1;

    saveDateStats(stats);

    addTurn(userInput, parsed.response, interest);

    // Send clean response
    res.json({
      response: parsed.response,
      interest: interest
    });

    // TTS only speaks the response text
    textToSpeech(parsed.response);
    saveInterest(interest);

  } catch (err) {
    console.error("Error generating response:", err);
    res.status(500).json({ error: "Failed to generate response" });
  }
});




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
  if (DISABLE_ROBOT_TTS) {
    console.log("Robot TTS disabled; skipping play.");
    return;
  }
  if (!ROBOT_PLAY_URL) {
    console.warn("M5CORE2_URL not set — skipping robot playback. Set M5CORE2_URL in .env");
    return;
  }
  try {
    await axios.post(ROBOT_PLAY_URL, {
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

    playOnRobot(`${AUDIO_HOST_URL}/tmp/audio.mp3`)
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "TTS failed" });
  }
});

async function textToSpeech(text) {
  try {
    console.log("Starting:", text)
    const voiceId = loadVoice();
    console.log("Load voice!", voiceId)
    /*
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

    playOnRobot(`${AUDIO_HOST_URL}/tmp/audio.mp3`)
    */
  } catch (error) {
    console.error("TTS Error:", error.response?.data || error.message);
  }
}

function extractAndParseJSON(result) {
  try {
    // 1️⃣ Get raw model text
    const rawText =
      result?.response?.candidates?.[0]?.content?.parts?.[0]?.text;

    if (!rawText) {
      throw new Error("No text returned from Gemini.");
    }

    // 2️⃣ Remove markdown fences if present
    let cleaned = rawText
      .replace(/```json/gi, "")
      .replace(/```/g, "")
      .trim();

    // 3️⃣ If Gemini accidentally added text before/after JSON,
    // extract the first {...} block
    const firstBrace = cleaned.indexOf("{");
    const lastBrace = cleaned.lastIndexOf("}");

    if (firstBrace === -1 || lastBrace === -1) {
      throw new Error("No valid JSON object found in response.");
    }

    cleaned = cleaned.slice(firstBrace, lastBrace + 1);

    // 4️⃣ Parse JSON
    const parsed = JSON.parse(cleaned);

    return parsed;

  } catch (err) {
    console.error("Failed to extract/parse Gemini JSON:", err);
    return null;
  }
}


app.get("/summary", async (req, res) => {
  try {

    const stats = loadDateStats();
    const context = loadContext();
    const formattedContext = context.turns.map((turn, index) => `Turn ${index + 1}:
      USER: ${turn.user}
      CHARACTER: ${turn.ai}

      Interest Before: ${index === 0 ? (stats.initialInterest || 0) : context.turns[index - 1].interest}
      Interest After: ${turn.interest}
    `).join("\n\n");


    const prompt = `You are a high-precision romantic performance analyst AI.

  You are evaluating ONE subject only:
  → The HUMAN USER.

  The USER just completed a simulated dinner date with a personality-driven AI CHARACTER.

  The USER is attempting to impress the CHARACTER.

  You are grading the USER'S performance only.

  ━━━━━━━━━━━━━━━━━━━━
  ROLE DEFINITIONS
  ━━━━━━━━━━━━━━━━━━━━

  USER:
  - The human participant
  - The one attempting to build attraction
  - The one being evaluated

  CHARACTER:
  - The simulated romantic interest
  - Exists only as a reaction signal
  - Is NOT being evaluated

  ━━━━━━━━━━━━━━━━━━━━
  CRITICAL EVALUATION RULES
  ━━━━━━━━━━━━━━━━━━━━

  1. Only analyze the USER.
  2. Never evaluate the CHARACTER.
  3. Never switch perspective.
  4. Refer to the USER in third person.
  5. The CHARACTER's responses exist only as feedback indicators.
  6. Interest score changes represent performance feedback.
  7. If you analyze the CHARACTER instead of the USER, the response is incorrect.
  8. If you mix up roles, the response is incorrect.
  9. Do NOT narrate from the CHARACTER perspective except in the final recap section.
  10. Be behaviorally specific. No generic advice.

  ━━━━━━━━━━━━━━━━━━━━
  YOUR OBJECTIVES
  ━━━━━━━━━━━━━━━━━━━━

  Analyze the USER'S romantic performance and:

  1. Identify the emotional arc driven by the USER
  2. Interpret the interest trajectory as performance feedback
  3. Identify USER behavioral strengths and weaknesses
  4. Detect USER-driven turning points
  5. Evaluate romantic compatibility based on USER behavior
  6. Provide actionable improvement advice for the USER
  7. Write a short dramatic recap from the CHARACTER'S perspective (based ONLY on USER behavior)
  8. Classify the date into a clear archetype
  9. Generate visualization metrics (0-100 scale)

  ━━━━━━━━━━━━━━━━━━━━
  INTEREST DATA (Performance Metrics)
  ━━━━━━━━━━━━━━━━━━━━

  ${JSON.stringify(stats, null, 2)}

  ━━━━━━━━━━━━━━━━━━━━
  CONVERSATION DATA (USER Performance Log)
  ━━━━━━━━━━━━━━━━━━━━

  The following is chronological interaction data.

  Each turn contains:
  - USER message
  - CHARACTER response
  - Interest score AFTER the turn

  ${formattedContext}

  ━━━━━━━━━━━━━━━━━━━━
  ANALYSIS REQUIREMENTS
  ━━━━━━━━━━━━━━━━━━━━

  - Reference specific USER behaviors.
  - Tie insights to interest score changes.
  - Interpret volatility meaningfully.
  - Identify causation patterns.
  - Do not be vague.
  - Do not be motivational.
  - Be analytical and observant.
  - Treat this as a performance review.

  ━━━━━━━━━━━━━━━━━━━━
  OUTPUT REQUIREMENTS
  ━━━━━━━━━━━━━━━━━━━━

  Return ONLY valid JSON.
  Do NOT include markdown.
  Do NOT include commentary.
  Do NOT include explanations outside JSON.
  Do NOT wrap in code blocks.
  Return raw JSON only.

  Use EXACTLY this schema:

  {
    "narrativeRecap": string,
    "interestInsights": {
      "trajectoryType": string,
      "momentum": "gaining" | "losing" | "unstable" | "flat",
      "volatilityInterpretation": string
    },
    "behaviorEvaluation": {
      "strengths": [string, string],
      "weaknesses": [string, string],
      "communicationStyle": string
    },
    "turningPoints": {
      "mostPositiveMoment": string,
      "mostNegativeMoment": string,
      "analysis": string
    },
    "improvementAdvice": {
      "primarySuggestion": string,
      "specificExampleLine": string
    },
    "compatibility": {
      "score": number,
      "wouldTextBack": "yes" | "maybe" | "unlikely",
      "chemistryLevel": string,
      "longTermPotential": string
    },
  }
    `

    const result = await model.generateContent(prompt);
    const parsedJSON = extractAndParseJSON(result);
    if (!parsedJSON) {
      return res.status(500).json({ error: "Failed to parse Gemini JSON" });
    }
    res.json({
      summary: stats,
      advancedSummary: parsedJSON
    });
  } catch (err) {
    console.error("Error fetching summary:", err);
    res.status(500).json({ error: "Failed to generate summary" });
  }
});

app.get("/clear", (req, res) => {
  clearPersonality(); // Modifty for proper removal
  res.json({ message: "Personality cleared" });
});

app.listen(SERVER_PORT, () => {
  console.log(`\n--- image_to_voice server ---`);
  console.log(`  Listening on       : 0.0.0.0:${SERVER_PORT}`);
  console.log(`  Detected LAN IP    : ${LOCAL_IP}`);
  console.log(`  Audio host URL     : ${AUDIO_HOST_URL}`);
  console.log(`  M5Core2 play URL   : ${ROBOT_PLAY_URL || "NOT SET  (set M5CORE2_URL in .env)"}`);
  console.log(`  Robot TTS disabled : ${DISABLE_ROBOT_TTS}`);
  console.log(`---\n`);
});
