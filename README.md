# 🎨 Color Highlight

Show color codes (like "#ffffff", 0xffffff "rgb(255, 255, 255)", "white",
hsl(0, 0%, 100%), etc.) with their real color as the background and gutter icons.

![Description](screenshots/screenshot.gif?raw=true)

## Installation

- **_Recommended_** - Using [Sublime Package Control](https://packagecontrol.io "Sublime Package Control")
    - <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> then select `Package Control: Install Package`
    - install `Color Highlight`
- Alternatively, download the package from [GitHub](https://github.com/Kronuz/ColorHighlight "ColorHighlight") into your `Packages` folder.


## Usage

Supported color representations are:

- Hexademical e.g. #RGB or #RRGGBB or #RRGGBBAA (you can use both upper and lower case letters)

- RBG or RGBA value e.g. rgb(rrr, ggg, bbb) or rgba(rrr, ggg, bbb, a.aaa) with decimal channel values.

- HSL or HSLA value e.g. hsl(hue, sat%, lum%) or hsla(hue, sat%, lum%, a.aaa).

- Hexadecimal numbers with prefix 0x like 0xRRGGBBAA

- Named colors like "green", "black" and many others are also supported.


Those will be shown with colored background and gutter icons when they're found in
your documents.


## Configuration

- Open settings using the command palette:
  `Preferences: ColorHighlight Settings - User`

- You can disable live highlight directly from the command palette:
  `ColorHighlight: Disable Color Highlight`


## Donate

[![Click here to lend your support to ColorHighlight and make a donation!](https://www.paypalobjects.com/en_GB/i/btn/btn_donate_LG.gif)](https://www.paypal.me/Kronuz/25)


## License

Copyright (C) 2018 German Mendez Bravo (Kronuz). All rights reserved.

MIT license

This plugin was initially a for of https://github.com/Monnoroch/ColorHighlighter
