/*
 * WiFi Configuration for SenseCAP Indicator
 *
 * Copy this file to wifi_config.h and fill in your WiFi credentials.
 *   cp wifi_config.example.h wifi_config.h
 *
 * wifi_config.h is gitignored so your credentials stay private.
 */

#pragma once

#define WIFI_SSID     "YOUR_SSID"
#define WIFI_PASSWORD "YOUR_PASSWORD"

// TCP server port for remote control
#define TCP_PORT      7777

// mDNS hostname — device will be reachable at sensecap.local
#define MDNS_HOSTNAME "sensecap"
