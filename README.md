# I Want Tickets

<a href="https://github.com/jonathanlo411/i-want-tickets/releases"><img src="https://img.shields.io/github/v/release/jonathanlo411/i-want-tickets?color=f56827"></a>
<a href="https://github.com/jonathanlo411/i-want-tickets/blob/main/LICENSE"><img src="https://img.shields.io/github/license/jonathanlo411/i-want-tickets"></a>

I Want Tickets is a utility script to increase chances at getting tickets by spinning up multiple lightweight containerized Chrome sessions.

## Overview
This was developed with the aim to get [Ghibili Museum](https://www.ghibli-museum.jp/en/tickets/) tickets as the ticket website goes by amount of devices rather than IP.

This does *NOT* work for websites that do more in depth profiling. These may include but are not limited to IP tracing, device fingerprint, and host OS. To mitigate most of these, you can use [VMWare Workstation Pro](https://www.vmware.com/products/desktop-hypervisor/workstation-and-fusion) which allows you to configure Guest OS as needed. However to mitigate IP you will need to VPN or use proxies.

## Setup
### Requirements
- Python 3
- Chrome
- Docker

### Usage
1. Clone repository.
2. (Optional) Create a Python virtual environment.
3. Install Python dependencies via `requirements.txt`.
4. Modify `config.json` to your use case.
5. Run `ticket.py`.
6. When done, Ctrl+C to shutdown containers. Close windows manually.

### Config Options
| Arg                  | Required | Options                            | Description                                                                                                                                                                                                                                                                                       |
|----------------------|----------|------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|     `browser_uri`    |    Yes   | Any valid URL                      | This will the URL that the browser opens. Put the link to your ticket website here. Ensure that no session information is stored in the URL parameters.                                                                                                                                           |
|    `browser_count`   |    No    | `0`, or any integer > `0`          | If this is `0` it will spin up an appropriate amount of browsers based on your available RAM. You can define a manual value otherwise.                                                                                                                                                            |
|    `browser_mode`    |    Yes   | `tabs`, `windows`                  | If set to `tabs`, a single browser with the count being tabs. If set to `windows`, the program will open them as seperate browsers and will orient them according to `screen_orientation`.                                                                                                        |
| `screen_orientation` |    No    | `double`, `triple`, `grid`, `auto` | This argument requires `browser_mode` to be set to `windows`.  If `double`, a side by side orientation will be set. If `triple`, a set of three columns will be set. If `grid`, a two by two grid of browsers will be set. If `auto`, an option will be selected based on your screen resolution. |

## License
This project is licensed under the MIT License. See `LICENSE` for more information.