const express = require('express');
const { exec } = require('child_process');
const fs = require('fs');
const app = express();

app.get('/user', (req, res) => {
  const id = req.query.id;
  db.query("SELECT * FROM users WHERE id = '" + id + "'", (err, rows) => {
    res.send('<h1>' + req.query.name + '</h1>');
  });
  db.query(`SELECT * FROM t WHERE n = ${req.body.name}`);
});

app.get('/ping', (req, res) => {
  const { host } = req.query;
  exec('ping -c 1 ' + host);
});

app.get('/go', (req, res) => {
  res.redirect(req.query.next);
});

app.get('/file', (req, res) => {
  fs.readFile('/srv/' + req.params.name, (e, d) => res.send(d));
});

app.get('/eval', (req, res) => { eval(req.query.code); });

document.getElementById('x').innerHTML = location.hash.slice(1);
const token = Math.random().toString(36);
res.cookie('session', token);
axios.get(req.query.url);
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
app.post('/transfer', (req, res) => { res.send('ok'); });
const session = require('express-session');
