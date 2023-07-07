#!/usr/bin/env python3

import subprocess
import re
import configparser
import argparse
import json
import os, sys
import psutil
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dateutil.parser import parse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText


class ServerCheck:
    '''
    The ServerCheck class holds all the parameters and methods required for checking information
    and relaying data to the user.
    '''
    def __init__(self, configfile = "config.ini"):
        '''
        Initialize an instance of ServerCheck.
        
        Parameters
        ----------
        configfile : string, optional
            file name of the configuration file (default: 'config.ini').

        Returns
        -------
        None.

        '''
        config = configparser.ConfigParser()
        config.read(configfile)
        
        # Monitoring parameters
        self.parameters = {
            'server': config.get('parameters', 'server'), # server name (for the e-mail message)
            'maxtemp': config.getint('parameters', 'maxtemp'),
            'maxcpu': config.getint('parameters', 'maxcpu'),
            'maxmem': config.getint('parameters', 'maxmem'),
            'maxdisk': config.getint('parameters', 'maxdisk'),
            'partitions': [s.strip() for s in config.get('parameters', 'partitions').split(',')],
            'datapoints': config.getint('parameters', 'datapoints')
        }
        
        # E-mail settings
        self.mailsettings = {
            'sender': config.get('email', 'sender'),
            'receiver': config.get('email', 'receiver'),
            'app_password': config.get('email', 'app_password'), # This is stored in clear in the .ini
            'mailserver': config.get('email', 'mailserver')
        }
        
            

    def check(self, args):
        '''
        Perform all necessary checks.
        
        Parameters
        ----------
        args : argparse.Namespace
            Parsed command-line arguments.
            
        Returns
        -------
        None.

        '''
        self.args = args
        
        # You can override the max temperature to a different value than the config.ini
        # (useful if you want to always replicate a system setting)
        self.override_message = ""
        if self.args.override is not None and self.parameters['maxtemp'] != self.args.override:
            self.override_message = f"Config.ini temperature of {self.parameters['maxtemp']} was overridden to {self.args.override}"
            self.parameters['maxtemp'] = self.args.override

        self._get_data()

        if self.args.alarm:
            self._send_email(subject=f"### ALARM ### on {self.parameters['server']}", message=f"Server {self.parameters['server']} is going down NOW!")
        elif self.args.notify:
            if not self._check_status(): # If there are no warnings
                self._send_email(subject=f"Status report on {self.parameters['server']}", message="All is fine!<br>")
        else:
            self._check_status()



    def _get_data(self):
        '''
        Retrieve all necessary data from both the system and the logfile.
        

        Returns
        -------
        None.

        '''
        self.tempinfo = self._get_temperatures()
        self.cpuinfo = self._get_cpu_usage()
        self.meminfo = self._get_memory_usage()
        self.diskinfo = self._get_disk_usage(self.parameters['partitions'])

        # Load past data, if available
        self.logfile = 'status_log.json'
        if os.path.exists(self.logfile):
            with open(self.logfile, 'r') as f:
                self.past_data = [json.loads(line) for line in f][-(self.parameters["datapoints"]):]
        else:
            self.past_data = []

        self._log_status() # this will also append the current datapoint to self.past_data
        


    def _check_status(self):
        '''
        Check current values of temperature, CPU, memory, and disk usage against thresholds;
        If any of them reach the threshold, send an e-mail.

        Returns
        -------
        bool
            True if any value reached the threshold.

        '''

        warning = ''
        near_threshold = []

        if self.parameters['maxtemp'] - max(self.tempinfo.values()) <= 2:
            near_threshold.append('Temperature')

        if self.parameters['maxcpu'] - self.cpuinfo <= 2:
            near_threshold.append('CPU usage')

        if self.parameters['maxmem'] - self.meminfo <= 2:
            near_threshold.append('Memory usage')

        for disk, usage in self.diskinfo.items():
            if self.parameters['maxdisk'] - usage <= 2:
                near_threshold.append(f'Disk usage ({disk})')

        if near_threshold:
            warning = f"Warning: The following metrics are within 2 points of their thresholds: <br>{', '.join(near_threshold)} <br>"
            self._send_email(subject=f"Warning: Status near threshold on {self.parameters['server']}", message=warning)
            
        if warning:
            return True
        else:
            return False


    def _plot_temperature(self, action="save"):
        '''
        Create a plot of temperature over time.

        Parameters
        ----------
        action : string, optional
            If "show", display the plot; if "save", save it to "temperature.png". The default is "save".

        Returns
        -------
        None.

        '''
        # Parse log file data into lists of dates and temperatures for each package
        dates = []
        tempinfo_list = []
        mindata = 100
        maxdata = self.parameters['maxtemp']
        for data in self.past_data:
            dates.append(parse(data['datetime']))
            tempinfo_list.append(data['tempinfo'])

        # Determine which packages we have data for
        packages = set()
        for tempinfo in tempinfo_list:
            packages.update(tempinfo.keys())
            
        plt.figure()  # new figure

        # For each package, create a list of temperatures and plot them
        for package in packages:
            temps = [tempinfo.get(package) for tempinfo in tempinfo_list]
            mindata = min([mindata, min(temps)])
            maxdata = max([maxdata, max(temps)])
            plt.plot_date(dates, temps, '-', label=package)

        # plot the maxtemp threshold as a straight line
        plt.axhline(y=self.parameters['maxtemp'], color='r', linestyle='--')

        plt.gcf().autofmt_xdate()  # Beautify the x-labels
        plt.autoscale(tight=True)  # Eliminate white spaces
        plt.grid(True)  # Add grid
        plt.title('Temperature Over Time')
        plt.xlabel('Date and Time')
        plt.ylabel('Temperature (°C)')
        plt.ylim(max(mindata-5, 0), min(maxdata+5, 100))
        plt.legend()

        if action == "show":
            plt.show()  # Display the plot
        else:
        #elif action == "save":
            plt.savefig("temperature.png")  # Save the plot as PNG
            
        plt.clf()  # clear the figure


    def _plot_disks(self, action="save"):
        '''
        Plot disk usage over time.

        Parameters
        ----------
        action : string, optional
            If "show", display the plot; if "save", save it to "disk_usage.png". The default is "save".

        Returns
        -------
        None.

        '''
        # Parse log file data into lists of dates and diskinfo dictionaries
        dates = []
        diskinfo_list = []
        mindata = 100
        maxdata = 0
        for data in self.past_data:
            dates.append(parse(data['datetime']))
            diskinfo_list.append(data['diskinfo'])

        # Determine which partitions we have data for
        partitions = set()
        for diskinfo in diskinfo_list:
            partitions.update(diskinfo.keys())
            
        plt.figure()  # new figure

        # For each partition, create a list of disk usage and plot them
        for partition in partitions:
            disk_usages = [diskinfo.get(partition) for diskinfo in diskinfo_list]
            mindata = min([mindata, min(disk_usages)])
            maxdata = max([maxdata, max(disk_usages)])
            plt.plot_date(dates, disk_usages, '-', label=partition)

        plt.gcf().autofmt_xdate()  # Beautify the x-labels
        plt.autoscale(tight=True)  # Eliminate white spaces
        plt.grid(True)  # Add a grid
        plt.title('Disk Usage Over Time')
        plt.xlabel('Date and Time')
        plt.ylabel('Disk Usage (%)')
        #plt.ylim(max(mindata-5, 0), min(maxdata+5, 100))
        plt.ylim(0, 100)
        plt.legend()

        if action == "show":
            plt.show()  # Display the plot
        else:
        #elif action == "save":
            plt.savefig("disk_usage.png")  # Save the plot as PNG
            
        plt.clf()  # clear the figure
            

    def _plot_cpu_mem(self, action="save"):
        '''
        Plot CPU and memory usage over time.

        Parameters
        ----------
        action : string, optional
            If "show", display the plot; if "save", save it to "cpu_mem_usage.png". The default is "save".

        Returns
        -------
        None.

        '''
        # Parse log file data into lists of dates and cpu/memory info
        dates = []
        cpuinfo_list = []
        meminfo_list = []
        mindata = 100
        maxdata = 0
        for data in self.past_data:
            dates.append(parse(data['datetime']))
            cpuinfo_list.append(data['cpuinfo'])
            meminfo_list.append(data['meminfo'])

            mindata = min([mindata, min(cpuinfo_list), min(meminfo_list)])
            maxdata = max([maxdata, max(cpuinfo_list), max(meminfo_list)])

        plt.figure()  # new figure

        plt.plot_date(dates, cpuinfo_list, '-', label='CPU Usage (%)')
        plt.plot_date(dates, meminfo_list, '-', label='Memory Usage (%)')

        plt.gcf().autofmt_xdate()  # Beautify the x-labels
        plt.autoscale(tight=True)  # Eliminate white spaces
        plt.grid(True)  # Add grid
        plt.title('CPU and Memory Usage Over Time')
        plt.xlabel('Date and Time')
        plt.ylabel('Usage (%)')
        #plt.ylim(max(mindata-5, 0), min(maxdata+5, 100))
        plt.ylim(0, 100)
        plt.legend()

        if action == "show":
            plt.show()  # Display the plot
        else:
        #elif action == "save":
            plt.savefig("cpu_mem_usage.png")  # Save the plot as PNG
            
        plt.clf()  # clear the figure


    def _send_email(self, subject="", message=""):
        '''
        Send an e-mail according to the parameters set in the config file.

        Parameters
        ----------
        subject : string, optional
            The e-mail subject. The default is "".
        message : string, optional
            The e-mail message (plots and data will be appended). The default is "".

        Returns
        -------
        None.

        '''
    
        sender = self.mailsettings['sender']
        receiver = self.mailsettings['receiver']
        app_password = self.mailsettings['app_password']
        mailserver = self.mailsettings['mailserver']
    
        # Generate data plots
        self._plot_temperature()
        self._plot_disks()
        self._plot_cpu_mem()
        
        # Add data to the message text
        data = self.override_message + "<br>"
        for key, value in self.tempinfo.items():
            data += f"Package {key} temperature: {value}ºC (limit: {self.parameters['maxtemp']}ºC) <br>"
        for key, value in self.diskinfo.items():
            data += f"Partition '{key}' usage: {value}%\n (limit: {self.parameters['maxdisk']}%) <br>"
        data += f"Memory usage: {int(self.meminfo)}%\n (limit: {self.parameters['maxmem']}%) <br>"
        data += f"CPU usage: {int(self.cpuinfo)}%\n (limit: {self.parameters['maxcpu']}%) <br>"
        
        message = message + data

        # Generate e-mail content
        msg = MIMEMultipart()
        if subject == "":
            subject = 'Server status report'
            message = 'Server status report'
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = receiver

        msg.preamble = 'This is a multi-part message in MIME format.'

        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)

        msg_text = MIMEText(message, 'html')
        msg_alternative.attach(msg_text)
        
        # Attach images to the email body
        for img_file in ["temperature.png", "disk_usage.png", "cpu_mem_usage.png"]:
            try:
                with open(img_file, 'rb') as file:
                    img = MIMEImage(file.read())
                    html_img = MIMEText('<html><body><img src="cid:{}"><body></html>'.format(img_file), 'html')
                    msg.attach(html_img)
                    img.add_header('Content-ID', '<{}>'.format(img_file))
                    msg.attach(img)
            except FileNotFoundError:
                msg.attach("Could not find image file {}<br>".format(img_file))

        # And send!
        try:
            server = smtplib.SMTP(mailserver)
            server.ehlo()
            server.starttls()
            server.login(sender, app_password)
            server.sendmail(sender, receiver, msg.as_string())
            server.close()
        except Exception as e:
            print('Something went wrong...', e)


    def _log_status(self):
        '''
        Append the current status to the logfile.

        Returns
        -------
        None.

        '''
        data = {
            'datetime': datetime.now().isoformat(),
            'tempinfo': self.tempinfo,
            'cpuinfo': self.cpuinfo,
            'meminfo': self.meminfo,
            'diskinfo': self.diskinfo
        }
        self.past_data.append(data)

        with open(self.logfile, 'w') as f:
            for log in self.past_data:
                f.write(json.dumps(log) + '\n')


    def _get_temperatures(self):
        '''
        Get current temperature data.

        Returns
        -------
        temperatures : TYPE
            DESCRIPTION.

        '''
        command = ["sensors"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"Error occurred: {stderr.decode('utf-8')}")
            return None

        output = stdout.decode('utf-8')

        # The 'sensors' command returns temperature values for 'packages' = CPUs
        matches = re.findall(r'Package id (\d+):\s+\+(\d+).0°C', output)
        temperatures = {package_id: int(temp) for package_id, temp in matches}

        return temperatures


    def _get_cpu_usage(self):
        '''
        Use psutil to get the current CPU usage.

        Returns
        -------
        cpu_usage : float
            A float representing the total CPU usage % at the current time.

        '''
        cpu_usage = psutil.cpu_percent(5)

        return cpu_usage


    def _get_memory_usage(self):
        '''
        Use psutil to get the current memory usage.

        Returns
        -------
        memory_usage : float
            The current memory usage.

        '''
        memory_usage = psutil.virtual_memory()[2]

        return memory_usage


    def _get_disk_usage(self, mountlist=["/", "/home"]):
        '''
        

        Parameters
        ----------
        mountlist : list, optional
            List of mount points to be returned. The default is ["/", "/home"].

        Returns
        -------
        disk_usage_info : dict
            A dictionary of mount points and their current usage, structured as {'/home': 70}.
            If the mount point was not found, the usage is None.

        '''
        command = ["df"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"Error occurred: {stderr.decode('utf-8')}")
            return None

        output = stdout.decode('utf-8')

        disk_usage_info = {}

        for line in output.splitlines():
            for mount in mountlist:
                if line.endswith(mount):
                    match = re.search(r'(\d+)%', line)
                    if match:
                        disk_usage_info[mount] = int(match.group(1))
                    else:
                        disk_usage_info[mount] = None

        return disk_usage_info


def parse_arguments():
    '''
    Parse command line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed command-line arguments.


    '''
    parser = argparse.ArgumentParser(description="Monitor server and send emails based on its status")
    group = parser.add_mutually_exclusive_group(required=False)
    # Main run options
    group.add_argument("-a", "--alarm", action="store_true", help="Explicitly send alarm e-mail about server shutdown")
    group.add_argument("-n", "--notify", action="store_true", help="Notify current server status by e-mail")
    group.add_argument("-c", "--check", action="store_true", help="Check server status and only send an e-mail if any warnings arise (default mode)")
    # Manually set temperature limit
    parser.add_argument('-o', '--override', type=int, help='Override config.ini maxtemp value to a different value (int)')
    return parser.parse_args()


def main():
    '''
    Execute the script.

    Returns
    -------
    None.

    '''
    args = parse_arguments()
    cwd = os.path.dirname(sys.argv[0])
    if cwd == '':
        cwd = '.'
    os.chdir(cwd)
    servercheck = ServerCheck(configfile="config.ini")
    servercheck.check(args)

if __name__ == "__main__":
    main()
