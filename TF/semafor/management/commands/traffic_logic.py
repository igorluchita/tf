import time
import cv2
import numpy as np
from django.core.management.base import BaseCommand
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import subprocess
import tempfile
import os
from pathlib import Path
from django.conf import settings

# Importă YOLO
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
    print("[init] YOLO available")
except ImportError:
    YOLO_AVAILABLE = False
    print("[init] YOLO not available")

# Importă GPIO
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
    print("[init] GPIO available")
except (ImportError, RuntimeError) as e:
    GPIO_AVAILABLE = False
    print(f"[init] GPIO not available: {e}")

FRAME_DIR = Path(settings.MEDIA_ROOT) / 'frames'
try:
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
except Exception as frame_err:
    print(f"[init] warning creating frame dir: {frame_err}")


class LEDController:
    """Controlează LED-urile pentru fiecare semafor"""
    
    def __init__(self, red_pin, yellow_pin, green_pin, name="Light"):
        self.red_pin = red_pin
        self.yellow_pin = yellow_pin
        self.green_pin = green_pin
        self.name = name
        self.current_state = 'off'
        
        if GPIO_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.red_pin, GPIO.OUT, initial=GPIO.LOW)
                GPIO.setup(self.yellow_pin, GPIO.OUT, initial=GPIO.LOW)
                GPIO.setup(self.green_pin, GPIO.OUT, initial=GPIO.LOW)
                print(f"[LED] {name} init: R={red_pin} Y={yellow_pin} G={green_pin}")
            except Exception as e:
                print(f"[LED] {name} error: {e}")
    
    def set_state(self, state):
        """Set LED state: 'red', 'yellow', 'green', 'off'"""
        if not GPIO_AVAILABLE:
            print(f"[LED] {self.name} mock: {state}")
            self.current_state = state
            return
        
        try:
            # Stinge toate
            GPIO.output(self.red_pin, GPIO.LOW)
            GPIO.output(self.yellow_pin, GPIO.LOW)
            GPIO.output(self.green_pin, GPIO.LOW)
            
            # Aprinde corect
            if state == 'red':
                GPIO.output(self.red_pin, GPIO.HIGH)
            elif state == 'yellow':
                GPIO.output(self.yellow_pin, GPIO.HIGH)
            elif state == 'green':
                GPIO.output(self.green_pin, GPIO.HIGH)
            
            self.current_state = state
        except Exception as e:
            print(f"[LED] {self.name} error: {e}")
    
    def cleanup(self):
        if GPIO_AVAILABLE:
            try:
                GPIO.output(self.red_pin, GPIO.LOW)
                GPIO.output(self.yellow_pin, GPIO.LOW)
                GPIO.output(self.green_pin, GPIO.LOW)
            except:
                pass


class TrafficLightController:
    """Controlează starea semaforelor și logica de semaforizare"""
    
    def __init__(self):
        self.light1_status = 'red'
        self.light2_status = 'red'
        self.light1_time_remaining = 0
        self.light2_time_remaining = 0
        self.vehicles1 = 0
        self.vehicles2 = 0
        self.priority1 = 'LOW'
        self.priority2 = 'LOW'
        
        # Parametri temporali
        self.GREEN_MAX_TIME = 15  # Timp maxim pentru verde
        self.YELLOW_TIME = 2      # Timp pentru galben
        
        # Stare mașinii de stări
        self.current_state = 'light1_green'
        self.state_start_time = time.time()
        
        # LED Controllers
        # Semafor 1: Red=17, Yellow=27, Green=22
        # Semafor 2: Red=23, Yellow=24, Green=25
        self.led1 = LEDController(red_pin=17, yellow_pin=27, green_pin=22, name="Light1")
        self.led2 = LEDController(red_pin=23, yellow_pin=24, green_pin=25, name="Light2")
        
        # YOLO model
        self.model = None
        if YOLO_AVAILABLE:
            try:
                print("[init] Loading YOLO model...")
                self.model = YOLO('yolov8n.pt')
                print("[init] YOLO model loaded")
            except Exception as e:
                print(f"[init] YOLO error: {e}")
                self.model = None
        
        # Cache
        self.use_libcamera_still = False
        self._check_libcamera()
        self.last_frames = {}
        
    def _check_libcamera(self):
        """Verifică dacă libcamera-still e disponibil"""
        try:
            result = subprocess.run(['which', 'libcamera-still'], capture_output=True, timeout=2)
            self.use_libcamera_still = result.returncode == 0
            print(f"[init] libcamera-still available: {self.use_libcamera_still}")
        except Exception as e:
            print(f"[init] libcamera check error: {e}")
    
    def detect_vehicles(self, camera_index, lane_key):
        """Detectează vehiculele cu YOLO și salvează frame-ul"""
        try:
            frame = None
            
            # Try libcamera-still (Raspberry Pi native)
            if self.use_libcamera_still:
                frame = self._capture_libcamera(camera_index)
            
            # Fallback OpenCV V4L2
            if frame is None:
                frame = self._capture_opencv(camera_index)
            
            # Fallback mock (pentru test fără cameră)
            if frame is None:
                frame = self._get_mock_frame(lane_key)
            
            if frame is None or frame.size == 0:
                return 0
            
            self.last_frames[lane_key] = frame
            self._save_frame(frame, lane_key)
            
            # YOLO detection
            if self.model is not None:
                return self._detect_with_yolo(frame)
            else:
                return self._detect_with_opencv(frame)
            
        except Exception as e:
            print(f"[detect] error: {e}")
            return 0
    
    def _capture_libcamera(self, camera_index):
        """Capture cu libcamera-still"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name
            
            cmd = ['libcamera-still', '-n', '--camera', str(camera_index), 
                   '-o', tmp_path, '--timeout', '100']
            
            result = subprocess.run(cmd, capture_output=True, timeout=3, text=True)
            
            if result.returncode == 0 and os.path.exists(tmp_path):
                frame = cv2.imread(tmp_path)
                os.unlink(tmp_path)
                if frame is not None:
                    return frame
            
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception as e:
            print(f"[libcamera] error: {e}")
        
        return None
    
    def _capture_opencv(self, camera_index):
        """Capture cu OpenCV V4L2"""
        try:
            cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
            if not cap.isOpened():
                return None
            
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            ret, frame = cap.read()
            cap.release()
            
            if ret and frame is not None:
                return frame
        except Exception as e:
            print(f"[opencv] error: {e}")
        
        return None
    
    def _get_mock_frame(self, lane_key):
        """Mock frame pentru test"""
        cached = self.last_frames.get(lane_key)
        if cached is not None:
            return cached
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def _save_frame(self, frame, lane_key):
        """Persistă frame-ul curent pentru afișare în dashboard"""
        if frame is None:
            return
        try:
            filename = FRAME_DIR / f"{lane_key}.jpg"
            cv2.imwrite(str(filename), frame)
        except Exception as e:
            print(f"[frames] error saving {lane_key}: {e}")
    
    def _detect_with_yolo(self, frame):
        """YOLO vehicle detection"""
        try:
            results = self.model(frame, verbose=False)
            
            # Vehicle classes: car=2, motorcycle=3, bus=5, truck=7
            vehicle_classes = [2, 3, 5, 7]
            vehicle_count = 0
            
            for result in results:
                for detection in result.boxes:
                    class_id = int(detection.cls[0])
                    confidence = float(detection.conf[0])
                    
                    if class_id in vehicle_classes and confidence > 0.5:
                        vehicle_count += 1
            
            print(f"[YOLO] detected {vehicle_count} vehicles")
            return min(vehicle_count, 9)
        except Exception as e:
            print(f"[YOLO] error: {e}")
            return 0
    
    def _detect_with_opencv(self, frame):
        """OpenCV fallback detection"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            vehicle_count = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 500:
                    vehicle_count += 1
            
            print(f"[OpenCV] detected {vehicle_count} vehicles")
            return min(vehicle_count, 9)
        except Exception as e:
            print(f"[OpenCV] error: {e}")
            return 0

    
    def get_priority(self, vehicle_count):
        """Prioritate bazată pe vehicule"""
        if vehicle_count == 0:
            return 'LOW'
        elif vehicle_count <= 2:
            return 'MED'
        else:
            return 'HIGH'
    
    def state_machine(self):
        """State machine pentru semafor cu GPIO control"""
        current_time = time.time()
        elapsed = current_time - self.state_start_time
        
        if self.current_state == 'light1_green':
            self.light1_status = 'green'
            self.light2_status = 'red'
            self.led1.set_state('green')
            self.led2.set_state('red')
            
            if elapsed >= self.GREEN_MAX_TIME or (self.vehicles2 > 0 and elapsed > 5):
                self.current_state = 'light1_yellow'
                self.state_start_time = current_time
        
        elif self.current_state == 'light1_yellow':
            self.light1_status = 'yellow'
            self.light2_status = 'red'
            self.led1.set_state('yellow')
            self.led2.set_state('red')
            
            if elapsed >= self.YELLOW_TIME:
                self.current_state = 'light2_green'
                self.state_start_time = current_time
        
        elif self.current_state == 'light2_green':
            self.light1_status = 'red'
            self.light2_status = 'green'
            self.led1.set_state('red')
            self.led2.set_state('green')
            
            if elapsed >= self.GREEN_MAX_TIME or (self.vehicles1 > 0 and elapsed > 5):
                self.current_state = 'light2_yellow'
                self.state_start_time = current_time
        
        elif self.current_state == 'light2_yellow':
            self.light1_status = 'yellow'
            self.light2_status = 'yellow'
            self.led1.set_state('yellow')
            self.led2.set_state('yellow')
            
            if elapsed >= self.YELLOW_TIME:
                self.current_state = 'light1_green'
                self.state_start_time = current_time
        
        # Calculează timer
        if self.current_state in ['light1_green', 'light1_yellow']:
            max_time = self.GREEN_MAX_TIME if self.current_state == 'light1_green' else self.YELLOW_TIME
            self.light1_time_remaining = max(0, int(max_time - elapsed))
            self.light2_time_remaining = 0
        else:
            max_time = self.GREEN_MAX_TIME if self.current_state == 'light2_green' else self.YELLOW_TIME
            self.light2_time_remaining = max(0, int(max_time - elapsed))
            self.light1_time_remaining = 0

    
    def get_data(self):
        """Returnează datele semaforului"""
        return {
            'light1_status': self.light1_status,
            'light2_status': self.light2_status,
            'vehicles1': self.vehicles1,
            'vehicles2': self.vehicles2,
            'timer1': self.light1_time_remaining,
            'timer2': self.light2_time_remaining,
            'priority1': self.priority1,
            'priority2': self.priority2,
        }
    
    def cleanup(self):
        """Cleanup resources"""
        self.led1.cleanup()
        self.led2.cleanup()
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
            except:
                pass


class Command(BaseCommand):
    help = 'Traffic light system with YOLO detection and GPIO LED control'

    def handle(self, *args, **options):
        print("🚦 Pornind sistemul de semaforizare cu YOLO și GPIO...")
        
        controller = TrafficLightController()
        channel_layer = get_channel_layer()
        
        CAMERA1_INDEX = 0
        CAMERA2_INDEX = 0
        
        last_update = time.time()
        
        try:
            while True:
                # Detectare vehicule
                controller.vehicles1 = controller.detect_vehicles(CAMERA1_INDEX, 'lane1')
                controller.vehicles2 = controller.detect_vehicles(CAMERA2_INDEX, 'lane2')
                
                # Prioritate
                controller.priority1 = controller.get_priority(controller.vehicles1)
                controller.priority2 = controller.get_priority(controller.vehicles2)
                
                # State machine cu GPIO
                controller.state_machine()
                
                # WebSocket broadcast
                if time.time() - last_update >= 1:
                    data = controller.get_data()
                    print(f"[ws] L1={data['light1_status']} V1={data['vehicles1']} | L2={data['light2_status']} V2={data['vehicles2']}")
                    
                    try:
                        async_to_sync(channel_layer.group_send)(
                            'traffic',
                            {
                                'type': 'traffic_update',
                                'message': data
                            }
                        )
                    except Exception as e:
                        print(f"[ws] error: {e}")
                    
                    last_update = time.time()
                
                time.sleep(0.5)
        
        except KeyboardInterrupt:
            print("\n✋ Oprire semafoare...")
            controller.cleanup()
        except Exception as e:
            print(f"❌ Eroare: {e}")
            import traceback
            traceback.print_exc()
            controller.cleanup()

