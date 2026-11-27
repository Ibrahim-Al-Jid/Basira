const express = require('express');
const { execFile } = require('child_process');
const app = express();
app.get('/user', (req, res) => {
  const id = parseInt(req.query.id, 10);
  db.query("SELECT * FROM users WHERE id = ?", [id], (err, rows) => {
    res.send('<h1>' + escapeHtml(req.query.name) + '</h1>');
  });
});
app.get('/go', (req, res) => {
  const next = req.query.next;
  if (!ALLOWED.includes(next)) return res.sendStatus(400);
  res.redirect(next);
});
el.textContent = location.hash.slice(1);
const token = crypto.randomBytes(16).toString('hex');
res.cookie('session', token, { httpOnly: true, secure: true });
