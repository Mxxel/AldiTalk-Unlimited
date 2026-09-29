# ALDI TALK Data Playwright Script#

## Welcome to my Aldi Talk Unlimited Script ##
After trying out the current solutions i wasnt satisfied.
Either it was me or the code, i dont know.
I just decided to develope my own script, before i get a vibe code flame, 
sure i used KI as helper here. It saved me alot of time, i just had to inspect the pages to find
CSS selectors which are consistent and feed it. Worked like a charm.


### Setup ###

Clone the repository.

Create and activate an virtual environment with python -m venv && source venv/bin/activate

Install the dependencies and Chromium:

```sh
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Copy `config.yaml.example` to `config.yaml`, set the phone number and password,
and choose `headless: false` or `headless: true`. 
I recommend personally to use headless true just to make sure everything works.
Set `delay-minimum` and `delay-maximum` to the refresh interval bounds in seconds, then run:

```sh
python alditalk.py
```
The script waits for the cookie consent dialog and clicks the button only when
both of these conditions match:

- `data-testid="uc-accept-all-button"`
- visible text `Alle akzeptieren`

It then follows the visible `Mein ALDI TALK` service link, accepts the second
consent dialog on `login.alditalk-kundenbetreuung.de`, fills the `Rufnummer`
field, waits five seconds, fills the password, and clicks the login control.
After the next page loads it accepts the next `Akzeptieren` consent dialog and
waits five seconds again.

The browser then stays open and refreshes after a random delay between 30 and
90 seconds. After each refresh it checks for both `Zahlung per Bankkonto` and
`Dein Guthaben:` to determine that it is on the correct page. 
If either marker is missing, it saves a full-page screenshot named `alditalk-unexpected-*.png` 
in the project directory and closes the browser. 
If a refresh shows `Sitzung abgelaufen. Bitte melde dich erneut an.`, the script fills both login fields,
submits the login form, waits five seconds, and resumes the refresh loop.

Also during each refresh loop, the `svg.usage-meter__graph` attribute (`aria-valuenow` below 50) is checked. 
If its value is below `3.5`, the visible circular action button is clicked, which provides you another 1GB.

If you encounter issues, feel free to open one.

Important:

Usage of it may be against the T & C of Aldi Talk and you may risk the ban
of your account. I am not responsible for that. This project is just to show what is possible with
modern technique in record time (compared to pre AI times).
