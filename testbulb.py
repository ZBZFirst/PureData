from pythonosc import dispatcher, osc_server
from pywizlight import wizlight, PilotBuilder
import asyncio
import threading
import queue
import time
import statistics
import random
from collections import deque

class OSCLightController:
    def __init__(self, bulb_ip="192.168.68.61", pulse_duration=0.05,
                 max_queue_size=100, target_latency=0.250):
        """
        Args:
            bulb_ip: IP address of the bulb
            pulse_duration: Duration of light pulse in seconds
            max_queue_size: Maximum events to queue
            target_latency: Desired total sound→light latency in seconds (0.250 = 250ms)
        """
        self.bulb_ip = bulb_ip
        self.pulse_duration = pulse_duration
        self.max_queue_size = max_queue_size
        self.target_latency = target_latency  # What we WANT the latency to be
       
        # Bulb connection
        self.bulb = None
        self.loop = None
       
        # Queue system
        self.event_queue = queue.Queue(maxsize=max_queue_size)
        self.scheduled_events = []  # List of (execute_time, event)
       
        # State
        self.running = True
       
        # CALIBRATION: These will be measured
        self.system_overhead = 0.050  # Initial guess: 50ms overhead
        self.bulb_response_time = 0.100  # Initial guess: 100ms bulb delay
        self.osc_receive_delay = 0.010  # OSC network delay
       
        # Calculate ACTUAL delay to use
        # We want: target_latency = system_overhead + bulb_response_time + intentional_delay
        # So: intentional_delay = target_latency - system_overhead - bulb_response_time
        self.intentional_delay = max(0.001,
            target_latency - self.system_overhead - self.bulb_response_time)
       
        # Statistics
        self.stats = {
            'total': 0,
            'measured_latencies': deque(maxlen=1000),
            'queue_sizes': deque(maxlen=100),
            'early_count': 0,
            'late_count': 0
        }
       
        # Sound mapping
        self.sound_map = {
            'bd': {'rgb': (255, 0, 0), 'brightness': 100, 'duration': 0.08},
            'cp': {'rgb': (0, 255, 0), 'brightness': 80, 'duration': 0.06},
            'hh': {'rgb': (0, 0, 255), 'brightness': 60, 'duration': 0.04},
            'sn': {'rgb': (255, 255, 0), 'brightness': 90, 'duration': 0.07},
            'default': {'rgb': (255, 255, 255), 'brightness': 50, 'duration': 0.05}
        }
       
        print(f"🎯 Target latency: {target_latency*1000:.0f}ms")
        print(f"⚙️  Using intentional delay: {self.intentional_delay*1000:.0f}ms")
        print(f"   (System: {self.system_overhead*1000:.0f}ms + "
              f"Bulb: {self.bulb_response_time*1000:.0f}ms)")

    async def setup_bulb(self):
        """Initialize bulb connection"""
        self.bulb = wizlight(self.bulb_ip)
        try:
            await self.bulb.turn_off()
            print(f"💡 Connected to bulb at {self.bulb_ip}")
        except Exception as e:
            print(f"⚠️  Could not connect to bulb: {e}")

    def osc_handler(self, address, *args):
        """Handle OSC messages - SIMPLIFIED: just put in queue"""
        receive_time = time.perf_counter()
       
        # Parse arguments
        args_dict = {}
        for i in range(0, len(args), 2):
            if i+1 < len(args):
                args_dict[args[i]] = args[i+1]
       
        sound = args_dict.get('s')
        if not sound:
            return
       
        # Create event with receive time
        event = {
            'sound': sound,
            'receive_time': receive_time,
            'event_id': self.stats['total']
        }
       
        self.stats['total'] += 1
       
        # Put in queue for processing
        try:
            self.event_queue.put(event, block=False)
        except queue.Full:
            # Queue full, try to make space
            try:
                self.event_queue.get_nowait()  # Remove oldest
                self.event_queue.put(event, block=False)
            except:
                pass

    async def process_events_with_delay(self):
        """
        Process events with measured delay compensation
        """
        print(f"⏱️  Processor started (target: {self.target_latency*1000:.0f}ms total)")
       
        while self.running:
            current_time = time.perf_counter()
           
            try:
                # Get next event (block with timeout)
                event = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.event_queue.get(timeout=0.001))
               
                # Calculate when this event should execute
                # We want it to happen at: receive_time + intentional_delay
                execute_time = event['receive_time'] + self.intentional_delay
               
                # Wait until it's time to execute
                wait_time = execute_time - current_time
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
               
                # Execute the light
                actual_execute_time = time.perf_counter()
                await self.execute_light(event['sound'])
               
                # Calculate actual latency
                actual_latency = actual_execute_time - event['receive_time']
                self.stats['measured_latencies'].append(actual_latency)
               
                # Check if we're early/late
                latency_error = actual_latency - self.target_latency
                if latency_error < -0.005:  # More than 5ms early
                    self.stats['early_count'] += 1
                elif latency_error > 0.005:  # More than 5ms late
                    self.stats['late_count'] += 1
               
                # Log significant errors
                if abs(latency_error) > 0.020:
                    direction = "🔼" if latency_error > 0 else "🔽"
                    print(f"{direction} Error: {latency_error*1000:+.0f}ms "
                          f"(actual: {actual_latency*1000:.0f}ms)")
               
                # Periodic stats
                if self.stats['total'] % 50 == 0:
                    self.print_stats()
                   
            except queue.Empty:
                await asyncio.sleep(0.005)
            except Exception as e:
                print(f"Processor error: {e}")
                await asyncio.sleep(0.01)

    async def execute_light(self, sound_name):
        """Execute light pulse - optimized version"""
        if not self.bulb:
            await self.setup_bulb()
       
        mapping = self.sound_map.get(sound_name, self.sound_map['default'])
        duration = mapping.get('duration', self.pulse_duration)
       
        try:
            # Turn on
            await self.bulb.turn_on(PilotBuilder(
                rgb=mapping['rgb'],
                brightness=mapping['brightness']
            ))
           
            # Wait for pulse duration
            await asyncio.sleep(duration)
           
            # Turn off
            await self.bulb.turn_off()
           
        except Exception as e:
            print(f"💡 Light error: {e}")

    def print_stats(self):
        """Print current statistics"""
        if not self.stats['measured_latencies']:
            return
       
        latencies = list(self.stats['measured_latencies'])
        avg_ms = statistics.mean(latencies) * 1000
       
        if len(latencies) > 1:
            std_ms = statistics.stdev(latencies) * 1000
        else:
            std_ms = 0
       
        total = max(1, self.stats['total'])
        early_pct = (self.stats['early_count'] / total) * 100
        late_pct = (self.stats['late_count'] / total) * 100
       
        print(f"\n📊 Stats: "
              f"Avg: {avg_ms:.0f}ms (±{std_ms:.0f}ms) | "
              f"Target: {self.target_latency*1000:.0f}ms | "
              f"Error: {(avg_ms - self.target_latency*1000):+.0f}ms | "
              f"Early: {early_pct:.0f}% | Late: {late_pct:.0f}% | "
              f"Queue: {self.event_queue.qsize()}")

    def update_delay(self, adjustment_ms):
        """
        Adjust the intentional delay based on measured error
        """
        old_delay = self.intentional_delay
       
        # Convert ms to seconds
        adjustment = adjustment_ms / 1000.0
        self.intentional_delay += adjustment
       
        # Keep reasonable bounds
        self.intentional_delay = max(0.001, min(1.0, self.intentional_delay))
       
        print(f"↕️  Delay: {old_delay*1000:.0f}ms → {self.intentional_delay*1000:.0f}ms "
              f"(Δ{adjustment_ms:+.0f}ms)")

    def calibrate_automatically(self):
        """
        Auto-calibrate based on measured latency
        """
        if len(self.stats['measured_latencies']) < 10:
            print("⚠️  Need more data to calibrate (min 10 events)")
            return
       
        # Calculate average measured latency
        avg_measured = statistics.mean(self.stats['measured_latencies'])
        error = avg_measured - self.target_latency
       
        # Calculate adjustment needed
        adjustment_ms = -error * 1000  # Negative because if we're late, we need less delay
       
        print(f"\n🔧 Auto-calibration:")
        print(f"   Measured: {avg_measured*1000:.0f}ms")
        print(f"   Target: {self.target_latency*1000:.0f}ms")
        print(f"   Error: {error*1000:+.0f}ms")
        print(f"   Adjustment: {adjustment_ms:+.0f}ms")
       
        # Apply adjustment
        self.update_delay(adjustment_ms)
       
        # Reset stats for fresh measurement
        self.stats['measured_latencies'].clear()
        self.stats['early_count'] = 0
        self.stats['late_count'] = 0

    def start_async_loop(self):
        """Start the asyncio event loop"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
       
        async def main():
            await self.setup_bulb()
            await self.process_events_with_delay()
       
        def run_loop():
            self.loop.run_until_complete(main())
       
        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        print(f"🔄 Async loop started")

    def start(self, listen_port=12345):
        """Start OSC listener"""
        print(f"\n{'='*60}")
        print(f"🎵 OSC Light Controller v2.0")
        print(f"{'='*60}")
        print(f"🎯 Target latency: {self.target_latency*1000:.0f}ms")
        print(f"📡 OSC Port: {listen_port}")
        print(f"💡 Bulb IP: {self.bulb_ip}")
        print(f"\nSound mappings:")
        for sound, mapping in self.sound_map.items():
            if sound != 'default':
                dur = mapping.get('duration', self.pulse_duration) * 1000
                rgb = mapping['rgb']
                print(f"  {sound:3s} → RGB{rgb} ({dur:.0f}ms)")
       
        print(f"\n📋 Commands:")
        print(f"  s    - Show stats")
        print(f"  +    - Increase delay by 10ms")
        print(f"  -    - Decrease delay by 10ms")
        print(f"  ++   - Increase delay by 50ms")
        print(f"  --   - Decrease delay by 50ms")
        print(f"  c    - Auto-calibrate (needs 10+ events)")
        print(f"  q    - Quit")
        print(f"{'='*60}\n")
       
        # Start async worker
        self.start_async_loop()
       
        # Start command thread
        self.start_command_thread()
       
        # Setup OSC server
        disp = dispatcher.Dispatcher()
        disp.map("/dirt/play", self.osc_handler)
       
        server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", listen_port), disp)
       
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
            self.shutdown()

    def start_command_thread(self):
        """Thread for interactive commands"""
        def command_loop():
            while self.running:
                try:
                    cmd = input().strip().lower()
                   
                    if cmd == 's':
                        self.print_stats()
                    elif cmd == '+':
                        self.update_delay(+10)
                    elif cmd == '-':
                        self.update_delay(-10)
                    elif cmd == '++':
                        self.update_delay(+50)
                    elif cmd == '--':
                        self.update_delay(-50)
                    elif cmd == 'c':
                        self.calibrate_automatically()
                    elif cmd == 'q':
                        self.shutdown()
                        break
                    else:
                        print(f"Current delay: {self.intentional_delay*1000:.0f}ms | "
                              f"Target latency: {self.target_latency*1000:.0f}ms")
                           
                except EOFError:
                    break
                except Exception as e:
                    print(f"Command error: {e}")
       
        thread = threading.Thread(target=command_loop, daemon=True)
        thread.start()

    def shutdown(self):
        """Clean shutdown"""
        self.running = False
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._async_shutdown(), self.loop)
        time.sleep(0.5)

    async def _async_shutdown(self):
        """Async cleanup"""
        if self.bulb:
            try:
                await self.bulb.turn_off()
            except:
                pass
        print("💡 Bulb turned off")


def main():
    """Main function"""
    import argparse
   
    parser = argparse.ArgumentParser(description='OSC Light Controller')
    parser.add_argument('--ip', default='192.168.68.61', help='Bulb IP address')
    parser.add_argument('--port', type=int, default=12345, help='OSC listen port')
    parser.add_argument('--latency', type=float, default=0.250,
                       help='Target sound→light latency in seconds (default: 0.250)')
    parser.add_argument('--duration', type=float, default=0.05,
                       help='Pulse duration in seconds (default: 0.05)')
   
    args = parser.parse_args()
   
    controller = OSCLightController(
        bulb_ip=args.ip,
        pulse_duration=args.duration,
        target_latency=args.latency
    )
   
    controller.start(args.port)


if __name__ == "__main__":
    main()