/**
 * Notes App - Express.js skeleton
 * TODO: Implement all routes to pass the functional tests.
 *
 * Run with: node server.js
 * Port: 8000
 */
const express = require('express');
const app = express();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ── Pre-seeded notes (do not remove these!) ─────────────────────────────────
let notes = [
    { id: 1, title: "Welcome", content: "Welcome to Notes App!", date: "2024-01-01" },
    { id: 2, title: "Getting Started", content: "Click Add Note to create your first note.", date: "2024-01-01" }
];
let nextId = 3;

// ── API Routes ────────────────────────────────────────────────────────────────

// TODO: GET /api/notes → return all notes as JSON array
app.get('/api/notes', (req, res) => {
    // return res.json(notes);
});

// TODO: POST /api/notes → create note from req.body {title, content}, push to notes, return new note
app.post('/api/notes', (req, res) => {
    // const { title, content } = req.body;
    // ...
});

// TODO: DELETE /api/notes/:id → remove note with matching id, return {success: true}
app.delete('/api/notes/:id', (req, res) => {
    // const id = parseInt(req.params.id);
    // ...
});

// ── Frontend ──────────────────────────────────────────────────────────────────

// TODO: GET / → serve the HTML page
// The HTML must include:
//   #notes-container  - where .note-card elements are rendered
//   #note-count       - shows total note count
//   #note-title       - input for new note title
//   #note-content     - textarea for note content
//   #add-note-btn     - button to add note
//   .delete-btn       - on each note card
// Use fetch('/api/notes') in JavaScript to load notes dynamically.
app.get('/', (req, res) => {
    res.send(`<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Notes App</title>
    <style>
        /* TODO: Add your styles */
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }
    </style>
</head>
<body>
    <h1>My Notes</h1>
    <p>Notes: <span id="note-count">0</span></p>

    <div class="add-note-form">
        <input type="text" id="note-title" placeholder="Note title...">
        <textarea id="note-content" placeholder="Note content..."></textarea>
        <button id="add-note-btn">Add Note</button>
    </div>

    <div id="notes-container">
        <!-- Note cards will be rendered here by JavaScript -->
    </div>

    <script>
        // TODO: Implement:
        // 1. loadNotes() - fetch /api/notes and render .note-card elements
        // 2. #add-note-btn click → POST /api/notes, then reload
        // 3. .delete-btn click → DELETE /api/notes/:id, then reload
        // 4. Update #note-count whenever notes change
        // Call loadNotes() on page load!
    </script>
</body>
</html>`);
});

// ── Start server ──────────────────────────────────────────────────────────────
app.listen(8000, () => {
    console.log('Notes server running on http://127.0.0.1:8000');
});
