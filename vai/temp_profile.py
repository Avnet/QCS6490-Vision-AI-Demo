import re
import glob
import os

def get_cpu_gpu_mem_temps():
    thermal_zones = {}
    gpu_temp = 35
    mem_temp = 35
    max_temp = 35
    for zone_path in glob.glob("/sys/class/thermal/thermal_zone*"):
        zone_id = os.path.basename(zone_path)
        try:
            with open(os.path.join(zone_path, "type"), "r") as f_type:
                zone_type = f_type.read().strip()
            with open(os.path.join(zone_path, "temp"), "r") as f_temp:
                try:
                    # Read the temperature value
                    f_tempValue = f_temp.read()
                except:
                    f_tempValue = None
                    
                if f_tempValue:
                    # Convert temperature from millidegrees Celsius to degrees Celsius
                    temp_millicelsius = int(f_tempValue.strip())
                    temp_celsius = temp_millicelsius / 1000.0
                    thermal_zones[zone_id] = {"type": zone_type, "temperature": temp_celsius}
                    
            if re.match(r'cpu\d+-thermal', zone_type):
                max_temp = max(max_temp, temp_celsius)
            elif zone_type == 'ddr-thermal':
                mem_temp = temp_celsius
            elif zone_type == 'video-thermal':
                gpu_temp = temp_celsius

        except FileNotFoundError:
            print(f"Warning: Could not find 'type' or 'temp' file for {zone_id}")
        except ValueError:
            print(f"Warning: Could not parse temperature for {zone_id}")
        except Exception as e:
            #print(f"An error occurred with {zone_id}: {e}")
            pass
    return max_temp, gpu_temp, mem_temp
