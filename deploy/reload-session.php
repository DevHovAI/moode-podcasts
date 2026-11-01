<?php
// Lädt moOdes Sendertabelle neu in die PHP-Sitzung – dieselben Aufrufe, die
// moOdes Worker beim Start macht (daemon/worker.php). Läuft als www-data über
// moode-podcasts-reload.service, damit die Sitzungsdatei www-data gehört.
require_once '/var/www/inc/common.php';
require_once '/var/www/inc/session.php';
require_once '/var/www/inc/sql.php';

if (phpSession('load_system') === false) {
	fwrite(STDERR, "moode-podcasts: Sitzung nicht geöffnet\n");
	exit(1);
}
phpSession('load_radio');
phpSession('close');
