# servercheck
Checks server status and sends an e-mail when any parameter reaches a predefined threshold.  
Part of the initial structure (in particular the plotting functions and the core of the e-mail sending function) was initially created via prompt engineering on ChatGPT, then expanded upon.  

## Requirements  
 - sensors: `sudo apt install lm-sensors` (for temperature reading)  

## Installation  
1. Clone the repository to a directory of your choosing.  

2. Rename/copy the `config.ini.example` file to `config.ini` and edit it to your liking.    
You will need to create an 'app password' (a 16-character code) and add it to the config.ini file, in order for the script to be able 
to send e-mail automatically:  
https://support.google.com/mail/answer/185833?hl=en  
Please note that the app password will allow a third party to impersonate your e-mail account, so it is fundamental that you keep the 'config.ini' file private.
E.g. use `chmod 550 config.ini` so that only administrators will be able to read it.  
I would advice to create a new e-mail address specifically for this purpose; be safe, do not use your main e-mail address for this!  

3. Create a cronjob running the script e.g. every 15 minutes:  
Type `crontab -e`  and append the following line to the file (adjust for the location of servercheck.py):  
```  
*/15 * * * * /usr/bin/python3 /home/myuser/.../servercheck/servercheck.py
```

Example report:  
(Command: `python3 servercheck.py --notify` after about 350 data points were collected):  
  
<img src="https://github.com/bioruffo/servercheck/assets/24945128/4db7429f-564b-424a-bd67-d5094aaddb8b" width=30% height=30%>
<img src="https://github.com/bioruffo/servercheck/assets/24945128/cf7e0b1c-69a2-4a94-aa51-0b0ff0824c51" width=30% height=30%>

