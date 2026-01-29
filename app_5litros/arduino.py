import serial
import time
import threading

class ArduinoController:
    def __init__(self, port='COM3', baudrate=9600):
        self.arduino = serial.Serial(port, baudrate, timeout=0.5)  # Short timeout
        time.sleep(2)  # Wait for Arduino reset
        
        # Clear any startup messages
        time.sleep(0.5)
        self.arduino.flushInput()
        print("Connected to Arduino")
    
    def set_delay(self, delay_ms):
        """Send delay command and wait for acknowledgment"""
        command = f"delay={delay_ms}\n"
        self.arduino.write(command.encode())
        
        # Wait for response with timeout
        start_time = time.time()
        while (time.time() - start_time) < 1.0:  # 1 second max wait
            if self.arduino.in_waiting > 0:
                response = self.arduino.readline().decode('utf-8').strip()
                print(f"Arduino: {response}")
                return True
        
        print("Warning: No response from Arduino")
        return False
    
    def get_delay(self):
        """Request current delay value"""
        self.arduino.write(b"get\n")
        time.sleep(0.1)
        
        if self.arduino.in_waiting > 0:
            response = self.arduino.readline().decode('utf-8').strip()
            print(f"Arduino: {response}")
    
    def close(self):
        self.arduino.close()

# Example 1: Interactive mode
def interactive_mode():
    controller = ArduinoController('COM3')  # Change to your port
    
    try:
        while True:
            user_input = input("\nEnter delay (ms) or 'get'/'quit': ")
            
            if user_input.lower() == 'quit':
                break
            elif user_input.lower() == 'get':
                controller.get_delay()
            else:
                try:
                    delay_value = int(user_input)
                    controller.set_delay(delay_value)
                except ValueError:
                    print("Invalid input")
    finally:
        controller.close()

# Example 2: Programmatic control (no blocking waits)
def programmatic_mode():
    controller = ArduinoController('COM3')
    
    # Set different delays automatically
    delays = [2000, 5000, 1000, 3000]
    
    for delay in delays:
        print(f"\nSetting delay to {delay}ms")
        controller.set_delay(delay)
        time.sleep(10)  # Wait before next change
    
    controller.close()

if __name__ == "__main__":
    interactive_mode()  # or programmatic_mode()
