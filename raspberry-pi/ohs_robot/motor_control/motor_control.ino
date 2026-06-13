// =====================================================================
//  OHS Robot - Motor Kontrol Firmware  (Arduino UNO + L298N + HC-SR04)
// ---------------------------------------------------------------------
//  HC-SR04 engel algilama + otomatik kacınma manevra eklendi.
//
//  MANEVRA:
//   Engel < OBSTACLE_CM iken FWD gidiyorsa:
//     1) Saga don  (TURN_90_MS)
//     2) 30cm ileri git (AVOID_FWD_MS)
//     3) Sola don  (TURN2_MS)    <- orijinal yone don
//     4) FWD'ye devam et
//
//  YENİ KOMUTLAR:
//   SONAR ON/OFF   engel kacınmayı ac/kapat
//   DIST           anlık mesafeyi cm olarak döndür
//
//  AYAR GEREKTİREN SABITLER:
//   TURN_90_MS   : 90 derece dönüş süresi — robotunu test edip ayarla
//   AVOID_FWD_MS : 30cm yan geçiş süresi — hızına göre ayarla
//   OBSTACLE_CM  : kaç cm'de engel sayılsın
// =====================================================================

#include <avr/wdt.h>

// ---- Motor Pinleri ----
#define ENA 5
#define IN1 6
#define IN2 7
#define IN3 8
#define IN4 9
#define ENB 10

// ---- HC-SR04 Pinleri ----
#define TRIG_PIN 11
#define ECHO_PIN 12

// ---- Motor Ayarları ----
uint8_t        baseSpeed          = 100;
const uint8_t  RAMP_STEP          = 6;
const uint16_t RAMP_PERIOD_MS     = 20;
const unsigned long HEARTBEAT_TIMEOUT = 2000;
const bool     USE_WATCHDOG       = true;

// ---- Engel Kaçınma Ayarları ----
const uint16_t OBSTACLE_CM    = 60;    // cm — engel eşiği
const uint16_t TURN_90_MS     = 300;   // ms — sağa dönüş
const uint16_t TURN2_MS       = 310;   // ms — sola dönüş
const uint16_t AVOID_FWD_MS   = 400;   // ms — kısa yan geçiş
const uint16_t AVOID_COOLDOWN = 2000;  // ms — kaçınma sonrası bekleme
const uint16_t SONAR_PERIOD   = 150;   // ms — sensör okuma periyodu

// ---- Trim ----
int8_t trimLeft  = 0;
int8_t trimRight = -15;

// ---- Durum ----
uint8_t resetFlags = 0;
enum Dir { STOPPED, FWD, BACK, LEFTT, RIGHTT };
Dir     curDir         = STOPPED;
bool    moving         = false;
bool    timed          = false;
unsigned long moveEndAt    = 0;
unsigned long lastRxAt     = 0;
bool    heartbeatArmed     = false;

// soft-start
uint8_t curSpeed    = 0;
unsigned long lastRampAt = 0;

// sonar
bool sonarEnabled    = true;
unsigned long lastSonarAt  = 0;
unsigned long lastAvoidAt  = 0;

// kaçınma state machine
enum AvoidState { AVOID_IDLE, AVOID_TURN1, AVOID_FWD_STATE, AVOID_TURN2 };
AvoidState    avoidState    = AVOID_IDLE;
unsigned long avoidPhaseEnd = 0;
bool          savedTimed    = false;
unsigned long savedMoveEndAt = 0;

// serial buffer
char    buf[40];
uint8_t bufLen = 0;

// =====================================================================
void setup() {
  resetFlags = MCUSR;
  MCUSR = 0;
  wdt_disable();

  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  hardStop();
  Serial.begin(115200);
  delay(300);
  Serial.println(F("READY"));
  printResetInfo();

  lastRxAt = millis();
  if (USE_WATCHDOG) wdt_enable(WDTO_2S);
}

// =====================================================================
void loop() {
  if (USE_WATCHDOG) wdt_reset();

  readSerial();
  updateRamp();

  // Süreli hareket bitti mi (kaçınma sırasında bu kontrolü atla)
  if (moving && timed && avoidState == AVOID_IDLE && (long)(millis() - moveEndAt) >= 0) {
    stopMove("TIME");
  }

  // Heartbeat failsafe
  if (heartbeatArmed && moving && (millis() - lastRxAt > HEARTBEAT_TIMEOUT)) {
    avoidState = AVOID_IDLE;
    stopMove("HEARTBEAT_TIMEOUT");
  }

  // Sonar: sadece ileri giderken ve kaçınma yokken kontrol et
  if (sonarEnabled && moving && curDir == FWD && avoidState == AVOID_IDLE) {
    if (millis() - lastSonarAt > SONAR_PERIOD &&
        millis() - lastAvoidAt > AVOID_COOLDOWN) {
      lastSonarAt = millis();
      uint16_t dist = readSonarCm();
      if (dist > 0 && dist < OBSTACLE_CM) {
        Serial.print(F("OBSTACLE "));
        Serial.print(dist);
        Serial.println(F("cm"));
        startAvoidance();
      }
    }
  }

  // Kaçınma manevrasını güncelle
  updateAvoidance();
}

// =====================================================================
// HC-SR04
// =====================================================================
uint16_t readSonarCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 25000); // 25ms timeout ~= 430cm
  if (duration == 0) return 999;
  return (uint16_t)(duration / 58);
}

// =====================================================================
// KAÇINMA MANEVRA STATE MACHINE
// =====================================================================
void startAvoidance() {
  // Mevcut hareketi kaydet
  savedTimed    = timed;
  savedMoveEndAt = moveEndAt;

  avoidState    = AVOID_TURN1;
  avoidPhaseEnd = millis() + TURN_90_MS;
  startMove(RIGHTT, TURN_90_MS);
}

void updateAvoidance() {
  if (avoidState == AVOID_IDLE) return;
  if ((long)(millis() - avoidPhaseEnd) < 0) return;

  switch (avoidState) {

    case AVOID_TURN1:                        // 90° sağa döndü → yan geç
      avoidState    = AVOID_FWD_STATE;
      avoidPhaseEnd = millis() + AVOID_FWD_MS;
      startMove(FWD, AVOID_FWD_MS);
      break;

    case AVOID_FWD_STATE:                    // yan geçti → sola dön
      avoidState    = AVOID_TURN2;
      avoidPhaseEnd = millis() + TURN2_MS;
      startMove(LEFTT, TURN2_MS);
      break;

    case AVOID_TURN2:                        // orijinal yöne döndü → devam
      avoidState  = AVOID_IDLE;
      lastAvoidAt = millis();
      Serial.println(F("AVOID_DONE"));

      if (savedTimed) {
        long remaining = (long)(savedMoveEndAt - millis());
        if (remaining > 0) {
          startMove(FWD, remaining);
        } else {
          stopMove("TIME");
        }
      } else {
        startMove(FWD, 0);   // süresiz devam
      }
      break;

    default: break;
  }
}

// =====================================================================
// SERIAL
// =====================================================================
void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (bufLen > 0) {
        buf[bufLen] = '\0';
        lastRxAt = millis();
        handleLine(buf);
        bufLen = 0;
      }
    } else if (bufLen < sizeof(buf) - 1) {
      buf[bufLen++] = c;
    } else {
      bufLen = 0;
    }
  }
}

void handleLine(char* line) {
  char* cmd = strtok(line, " ");
  char* a1  = strtok(NULL, " ");
  char* a2  = strtok(NULL, " ");
  if (!cmd) return;

  if      (!strcmp(cmd, "PING"))    { heartbeatArmed = true; Serial.println(F("PONG")); }
  else if (!strcmp(cmd, "FWD"))     { startMove(FWD,    a1 ? atol(a1) : 0); ack(cmd); }
  else if (!strcmp(cmd, "BACK"))    { startMove(BACK,   a1 ? atol(a1) : 0); ack(cmd); }
  else if (!strcmp(cmd, "LEFT"))    { startMove(LEFTT,  a1 ? atol(a1) : 0); ack(cmd); }
  else if (!strcmp(cmd, "RIGHT"))   { startMove(RIGHTT, a1 ? atol(a1) : 0); ack(cmd); }
  else if (!strcmp(cmd, "STOP"))    { avoidState = AVOID_IDLE; stopMove("CMD"); }
  else if (!strcmp(cmd, "SPEED"))   {
    if (a1) { baseSpeed = constrain(atoi(a1), 0, 255); }
    Serial.print(F("ACK SPEED ")); Serial.println(baseSpeed);
  }
  else if (!strcmp(cmd, "TRIM"))    {
    if (a1) trimLeft  = constrain(atoi(a1), -80, 80);
    if (a2) trimRight = constrain(atoi(a2), -80, 80);
    Serial.print(F("ACK TRIM L=")); Serial.print(trimLeft);
    Serial.print(F(" R="));         Serial.println(trimRight);
  }
  else if (!strcmp(cmd, "SONAR"))   {
    if (a1) {
      sonarEnabled = (!strcmp(a1, "ON") || !strcmp(a1, "on") || !strcmp(a1, "1"));
    }
    Serial.print(F("ACK SONAR ")); Serial.println(sonarEnabled ? F("ON") : F("OFF"));
  }
  else if (!strcmp(cmd, "DIST"))    {
    uint16_t d = readSonarCm();
    Serial.print(F("DIST "));
    if (d >= 999) Serial.println(F("NOECHO"));
    else          { Serial.print(d); Serial.println(F("cm")); }
  }
  else if (!strcmp(cmd, "STATUS"))    { printStatus(); }
  else if (!strcmp(cmd, "RESETINFO")) { printResetInfo(); }
  else { Serial.print(F("ERR UNKNOWN ")); Serial.println(cmd); }
}

void ack(const char* c) { Serial.print(F("ACK ")); Serial.println(c); }

// =====================================================================
// HAREKET
// =====================================================================
void startMove(Dir d, long ms) {
  curDir = d;
  setDirection(d);
  curSpeed   = 0;
  applySpeed();
  moving     = true;
  timed      = (ms > 0);
  moveEndAt  = millis() + (unsigned long)ms;
  lastRampAt = millis();
}

void stopMove(const char* reason) {
  hardStop();
  moving = false;
  timed  = false;
  curDir = STOPPED;
  Serial.print(F("STOPPED ")); Serial.println(reason);
}

void updateRamp() {
  if (!moving) return;
  uint8_t target = baseSpeed;
  if (curSpeed < target && (millis() - lastRampAt) >= RAMP_PERIOD_MS) {
    int s = curSpeed + RAMP_STEP;
    if (s > target) s = target;
    curSpeed = s;
    applySpeed();
    lastRampAt = millis();
  }
}

void applySpeed() {
  int l = constrain((int)curSpeed + trimLeft,  0, 255);
  int r = constrain((int)curSpeed + trimRight, 0, 255);
  analogWrite(ENB, l);  // ENB = fiziksel sol motor
  analogWrite(ENA, r);  // ENA = fiziksel sağ motor
}

void setDirection(Dir d) {
  switch (d) {
    case FWD:    digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW);  digitalWrite(IN3,HIGH); digitalWrite(IN4,LOW);  break;
    case BACK:   digitalWrite(IN1,LOW);  digitalWrite(IN2,HIGH); digitalWrite(IN3,LOW);  digitalWrite(IN4,HIGH); break;
    case LEFTT:  digitalWrite(IN1,LOW);  digitalWrite(IN2,HIGH); digitalWrite(IN3,HIGH); digitalWrite(IN4,LOW);  break;
    case RIGHTT: digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW);  digitalWrite(IN3,LOW);  digitalWrite(IN4,HIGH); break;
    default:     digitalWrite(IN1,LOW);  digitalWrite(IN2,LOW);  digitalWrite(IN3,LOW);  digitalWrite(IN4,LOW);  break;
  }
}

void hardStop() {
  setDirection(STOPPED);
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
  curSpeed = 0;
}

// =====================================================================
// RAPORLAR
// =====================================================================
void printResetInfo() {
  Serial.print(F("RESET_CAUSE "));
  if (resetFlags & (1 << WDRF))  Serial.print(F("WATCHDOG "));
  if (resetFlags & (1 << BORF))  Serial.print(F("BROWNOUT "));
  if (resetFlags & (1 << EXTRF)) Serial.print(F("EXTERNAL "));
  if (resetFlags & (1 << PORF))  Serial.print(F("POWERON "));
  if (resetFlags == 0)            Serial.print(F("NONE"));
  Serial.println();
}

void printStatus() {
  Serial.print(F("STATUS dir="));
  switch (curDir) {
    case FWD:    Serial.print(F("FWD"));   break;
    case BACK:   Serial.print(F("BACK"));  break;
    case LEFTT:  Serial.print(F("LEFT"));  break;
    case RIGHTT: Serial.print(F("RIGHT")); break;
    default:     Serial.print(F("STOP"));  break;
  }
  Serial.print(F(" speed="));  Serial.print(curSpeed);
  Serial.print(F(" base="));   Serial.print(baseSpeed);
  Serial.print(F(" trimL="));  Serial.print(trimLeft);
  Serial.print(F(" trimR="));  Serial.print(trimRight);
  Serial.print(F(" sonar="));  Serial.print(sonarEnabled ? F("ON") : F("OFF"));
  Serial.print(F(" avoid="));  Serial.print(avoidState != AVOID_IDLE ? F("ACTIVE") : F("IDLE"));
  Serial.print(F(" hb="));     Serial.print(heartbeatArmed ? F("ON") : F("OFF"));
  Serial.println();
}
