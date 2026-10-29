# BRP CAN Bus DTC Retrieval Protocol Details

## 1. Protocol Overview
BRP vehicles (Sea-Doo, Can-Am, Ski-Doo) generally utilize two main diagnostic protocols depending on the ECU generation:

*   **Siemens/Continental VDO ECU (approx. Pre-2010):** Uses **KWP2000 (ISO 14230)** mapped onto CAN.
*   **Bosch ECU (approx. Post-2010):** Uses **UDS (ISO 14229)** over ISO-TP (ISO 15765).

## 2. CAN Identifiers (Addressing)
The standard diagnostics usually occur on the standard OBD-II / ISO 15765 addresses, but manufacturer-specific modes exist.

*   **Request ID (Tool -> ECU):** `0x7E0` (Primary Engine ECU), `0x7E1` (Cluster), `0x7E2` (iBR/ABS).
    *   *Note:* Some older KW2000 systems may respond to `0x600` or broadcast proprietary frames, but `0x7E0` is the standard entry point.
*   **Response ID (ECU -> Tool):** `0x7E8` (Engine), `0x7E9` (Cluster), `0x7EA` (iBR).

## 3. Retrieving DTCs (Diagnostic Trouble Codes)

### A. Bosch Systems (UDS Protocol)
**Service:** `0x19` (Read DTC Information)

1.  **Wake-Up & Session:**
    *   Send **Tester Present**: `02 3E 00 ...` (ID: `0x7E0`)
    *   **Start Extended Session**: `02 10 03 ...` (ID: `0x7E0`)
    *   *Response:* `06 50 03 ...` (Positive Ack)

2.  **Request Active DTCs:**
    *   **Command:** `0x19` (ReadDTCInformation)
    *   **Sub-function:** `0x02` (ReportDTCByStatusMask)
    *   **Status Mask:** `0x09` (Request "Confirmed" and "Pending" faults) or `0xFF` (All).
    *   **Packet (ISO-TP Single Frame):**
        ```hex
        ID: 0x7E0
        DLC: 8
        Data: 03 19 02 09 00 00 00 00
        ```
        *(Explanation: 03=Length, 19=Service, 02=SubFunc, 09=Mask)*

3.  **Decoding Response:**
    *   **Positive Response:** `59 02 (Status) (DTC1_High) (DTC1_Middle) (DTC1_Low) (Status) ...`
    *   *Note on UDS DTC Format:* 3 bytes per DTC.
        *   Byte 1: Type (P, C, B, U) and 1st digit.
            *   `0x00`-`0x3F`: P-Code (Powertrain)
            *   `0x40`-`0x7F`: C-Code (Chassis)
            *   `0x80`-`0xBF`: B-Code (Body)
            *   `0xC0`-`0xFF`: U-Code (Network)
        *   Byte 2: 2nd & 3rd digits.
        *   Byte 3: 4th & 5th digits equivalents (Specific fault).

### B. Siemens Systems (KWP2000 Protocol)
**Service:** `0x18` (Read DTC By Status)

1.  **Wake-Up & Initialization:**
    *   **Start Communication:** `0x81`
    *   **Packet:** `02 81 01 ...` (ID: `0x7E0`)
    *   *Response:* `06 C1 ...` or `02 C1 ...`

2.  **Request Active DTCs:**
    *   **Command:** `0x18`
    *   **Group:** `0x00` (All Groups)
    *   **Packet:**
        ```hex
        ID: 0x7E0
        DLC: 8
        Data: 04 18 00 FF 00 00 00 00
        ```
    *   *Note:* `FF 00` is often the Group/High/Low parameter wrapper.

3.  **Decoding Response:**
    *   **Positive Response:** `58 (Count) (DTC_High) (DTC_Low) (Status) ...`
    *   KWP usually returns 2 bytes for the DTC + 1 byte for status.

## 4. Fault Code vs. Action Code
*   **P-Codes (DTC):** The internal engineering codes (e.g., `P0123`).
*   **Action Codes:** User-facing codes displayed on the gauge cluster (e.g., often just "Check Engine" or a simpler numeric code on older skis).
*   **Conversion:** The cluster (`0x7E1`) often listens to the ECU broadcast or requests the DTCs and performs an internal lookup table to display the "Action Code".
    *   To deduce the mapping, one must usually read the raw P-Code from `0x7E0` and compare it with the Service Manual's list of P-Codes to Action Codes.

## 5. Summary of Construction Steps
1.  **Initialize:** Send Wake-Up (`0x3E` or `0x81`).
2.  **Request:** Send `03 19 02 09 ...` (UDS) to `0x7E0`.
3.  **Receive:** Listen on `0x7E8`. Handle ISO-TP Multi-frame flow control if response > 7 bytes.
    *   *ISO-TP Flow Control:* If first byte is `0x10` (First Frame), you must send `0x30 0x00 0x00 ...` (Flow Control) to receive the rest.
4.  **Parse:** Extract 3-byte hex chunks and format as `Pxxxx`.
