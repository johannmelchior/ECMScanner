# BRP (Sea-Doo/Ski-Doo) CAN Bus Protocol Research Summary

## 1. Siemens/Continental VDO (approx. 2004-2010)
**Filesystem:** MSE 3.7 / 3.7 R
**Engine:** Rotax 4-TEC (1503)

### Protocol Details
*   **Protocol:** KWP2000 (Key Word Protocol 2000) - ISO 14230-4 mapped to CAN (similar to ISO 15765-4 but often with manufacturer specific timing or addressing).
*   **Baud Rate:** 500 kbps (Standard for almost all BRP vehicles).
*   **CAN ID Format:** 11-bit Standard Identifiers.

### Initialization & Wake-Up
*   **Physical Wake-Up:** These ECUs revert to a low-power "Sleep" mode very quickly (typically 30-60 seconds) after the engine stops or the DESS key is removed. To initiate communication without the engine running, the physical "Start/Stop" button on the handlebar must often be tapped once to energize the main relay.
*   **Software "Keep-Alive":** Once awake, the diagnostic tool must establish a session immediately, otherwise the ECU will time out and power down.
*   **Initialization Sequence (KWP Start Communication):**
    *   **Service:** `0x81` (Start Communication)
    *   **Tester ID (Request):** `0x7E0` (Common default) or `0x600` (Manufacturer specific variants).
    *   **ECU ID (Response):** `0x7E8` or `0x601`.
    *   **KWP Init Frame Example:**
        *   ID: `0x7E0`
        *   Data: `0x02 0x81 0x01 0x00 0x00 0x00 0x00 0x00` (Length 2, Service 0x81, Mode)
        *   *Note:* Some earlier proprietary versions use the ID pair `0x011` / `0x012` or `0x020` range for non-standard comms.

### Key CAN IDs to Monitor
*   **Arbitration IDs:** `0x110` - `0x650` range.
*   **Broadcast Data (Engine Running):**
    *   RPM, Throttle, Temp are often broadcast on IDs like `0x100`, `0x200`, `0x400`.
    *   Look for inter-module communication (Cluster <-> ECU).

---

## 2. Bosch (Post-2010/2011)
**Filesystem:** Motronic ME17.8.5
**Engine:** Rotax 900 ACE, 1630 ACE, etc.

### Protocol Details
*   **Protocol:** UDS (Unified Diagnostic Services) - ISO 14229 over ISO-TP (ISO 15765-2).
*   **Baud Rate:** 500 kbps (500,000 baud).
*   **CAN ID Format:** 11-bit Standard (mostly) and 29-bit Extended (for vehicular broadcasts).

### Initialization & Session Start
*   **Physical Wake-Up:** Same as Siemens. Tap the Start button to energize the system.
*   **Session Control (UDS Service 0x10):**
    *   To start a diagnostic session, you must transition from "Default Session" to "Extended Diagnostic Session" or "Programming Session".
*   **Addressing:**
    *   **Request ID (Tester -> ECU):** `0x7E0`
    *   **Response ID (ECU -> Tester):** `0x7E8`
*   **Initialization Frames (UDS):**
    1.  **Tester Present (Keep Alive):**
        *   ID: `0x7E0`
        *   Data: `0x02 0x3E 0x00 0x00 0x00 0x00 0x00 0x00` (Service 3E, Sub-function 00 - periodic)
        *   *Send this every 2000ms to keep ECU awake.*
        
    2.  **Start Extended Session:**
        *   ID: `0x7E0`
        *   Data: `0x02 0x10 0x03 0x00 0x00 0x00 0x00 0x00` (Service 10, Session 03 - Extended)
        *   *ECU Response:* `0x06 0x50 0x03 ...` (Positive Response + Session Params)

    3.  **Security Access (Seed/Key) - Required for critical functions:**
        *   Service `0x27`. usually Level 0x01 (Request Seed) / 0x02 (Send Key).
        *   Algorithms are proprietary to BRP (Seed/Key exchange).

### Key CAN IDs to Monitor
*   **Diagnostics:** `0x7E0` (Engine ECU), `0x7E1` (Cluster/Info Center), `0x7E2` (iBR - Brake/Reverse).
*   **Broadcast Data (J1939-like or Proprietary):**
    *   Bosch systems often use 29-bit Extended IDs for broadcasts that resemble SAE J1939 but with custom PGNs.
    *   Look for IDs like `0x18FE...` or `0x0CF0...` if they follow standard J1939 (Torque/Speed).
    *   Proprietary broadcasts often appear in the `0x200`-`0x500` (11-bit) range for backward compatibility with clusters.

## Summary for ESP32 Implementation

To build a universal "BRP Wake-up/Reader" tool:

1.  **Configure MCP2515:**
    *   **Speed:** 500 kbps.
    *   **Masks/Filters:** Open (listen to all) initially to sniff traffic.

2.  **Wake-Up Strategy:**
    *   Display message to user: "Tap Start Button once to wake vehicle".
    *   **Immediately** start sending "Tester Present" messages (`0x3E`) on ID `0x7E0` every 1-2 seconds.

3.  **ECU Identification:**
    *   Try sending UDS Session Request (`0x10 0x03`) to `0x7E0`.
    *   If no response, try KWP Init (`0x81`) to `0x7E0` or `0x600`.
    *   If response received, lock onto that protocol.
