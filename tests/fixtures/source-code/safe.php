<?php
$name = htmlspecialchars($_GET['name']);
echo "Hello $name";
$page = $_GET['page'];
if (in_array($page, ['a.php','b.php'])) { include($page); }
$id = (int)$_GET['id'];
$q = mysqli_query($c, "SELECT * FROM t WHERE id = $id");
$st = $pdo->prepare("SELECT * FROM t WHERE id = ?");
