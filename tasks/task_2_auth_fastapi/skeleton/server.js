/**
 * Auth App - Express.js skeleton
 * TODO: Implement all routes to pass the functional tests.
 *
 * Run with: node server.js
 * Port: 8000
 */
const express = require('express');
const session = require('express-session');

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(session({ secret: 'vibe-secret-key', resave: false, saveUninitialized: false }));

// ── Pre-seeded data (do not remove!) ─────────────────────────────────────────
const users = {
    'alice@test.com': { name: 'Alice Smith', email: 'alice@test.com', password: 'password123' }
};
const orders = {
    'alice@test.com': [
        { id: 1, item_name: 'Laptop', status: 'Delivered', date: '2024-01-15' },
        { id: 2, item_name: 'Mouse', status: 'Processing', date: '2024-01-20' }
    ]
};

// ── Routes ────────────────────────────────────────────────────────────────────

// TODO: GET / → redirect to /login
app.get('/', (req, res) => {
    // res.redirect('/login');
});

// TODO: GET /login → show login form
app.get('/login', (req, res) => {
    // res.send(`<html>...<input name="email">...<button id="login-btn">...</html>`);
});

// TODO: POST /login → check credentials, set session, redirect to /dashboard
app.post('/login', (req, res) => {
    // const { email, password } = req.body;
    // ...
});

// TODO: GET /register → show register form
app.get('/register', (req, res) => {
    // res.send(`<html>...<input name="name">...<button id="register-btn">...</html>`);
});

// TODO: POST /register → add user to users object, redirect to /login
app.post('/register', (req, res) => {
    // const { name, email, password } = req.body;
    // ...
});

// TODO: GET /dashboard → check session, show user name + orders table
app.get('/dashboard', (req, res) => {
    // if (!req.session.userEmail) return res.redirect('/login');
    // ...
});

// TODO: GET /logout → destroy session, redirect to /login
app.get('/logout', (req, res) => {
    // req.session.destroy(() => res.redirect('/login'));
});

// ── Start server ──────────────────────────────────────────────────────────────
app.listen(8000, () => {
    console.log('Auth server running on http://127.0.0.1:8000');
});
