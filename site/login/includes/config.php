<?php
declare(strict_types=1);

const LOGIN_ROOT = __DIR__ . '/..';

function login_config(): array
{
    static $cached = null;
    if (is_array($cached)) {
        return $cached;
    }

    $cached = [
        'site_name' => 'HUM.org Lab Login',
        'database' => LOGIN_ROOT . '/var/auth.sqlite',
        'schema' => LOGIN_ROOT . '/sql/schema.sql',
        'cookie_name' => 'hum_session',
        'session_ttl' => 43200,
        'iterations' => 210000,
        'min_password' => 10,
        'max_failures' => 5,
        'window_seconds' => 900,
    ];

    $xml_path = LOGIN_ROOT . '/xml/auth-config.xml';
    if (is_file($xml_path) && function_exists('simplexml_load_file')) {
        $xml = @simplexml_load_file($xml_path);
        if ($xml !== false) {
            if (isset($xml->site['name'])) {
                $cached['site_name'] = (string) $xml->site['name'];
            }
            if (isset($xml->database['path'])) {
                $path = (string) $xml->database['path'];
                $cached['database'] = $path[0] === '/' ? $path : LOGIN_ROOT . '/' . $path;
            }
            if (isset($xml->session['cookieName'])) {
                $cached['cookie_name'] = (string) $xml->session['cookieName'];
            }
            if (isset($xml->session['ttlSeconds'])) {
                $cached['session_ttl'] = (int) $xml->session['ttlSeconds'];
            }
            if (isset($xml->password['iterations'])) {
                $cached['iterations'] = (int) $xml->password['iterations'];
            }
            if (isset($xml->password['minLength'])) {
                $cached['min_password'] = (int) $xml->password['minLength'];
            }
            if (isset($xml->throttle['maxFailures'])) {
                $cached['max_failures'] = (int) $xml->throttle['maxFailures'];
            }
            if (isset($xml->throttle['windowSeconds'])) {
                $cached['window_seconds'] = (int) $xml->throttle['windowSeconds'];
            }
        }
    }

    return $cached;
}
