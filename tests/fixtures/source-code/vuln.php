<?php
$name = $_GET['name'];
echo "Hello $name";
include($_GET['page']);
$r = unserialize($_COOKIE['data']);
eval($_POST['code']);
$ch = curl_init($_GET['url']);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
$res = file_get_contents($_GET['file']);
header("Location: " . $_GET['to']);
