# Artwork showcase — end user guide

The **Artwork showcase** lets gallery staff open a **customer-friendly preview** of artwork images already stored in Masterpiece, and choose a **presentation scene** label (for example “Gallery — white wall”) that describes how the work might be shown.

This guide is for **operators** using the Copilot widget. It does not cover ERP administration or API configuration.

---

## What you need

- You must be **logged in** to the Copilot widget with the same company session you use for AI Insights (your IT team usually opens the widget from the ERP or sets this up for you).
- Your organization must have **enabled** the showcase feature (if you are sent to the main dashboard instead of the showcase page, the feature may be off — ask your administrator).

---

## Opening the showcase from a link

Your ERP or a colleague may send a link similar to:

`…/#/showcase/inventory?itemId=12345`

The number after **`itemId=`** is the inventory record for that artwork.

- If **`itemId`** is missing, the page will tell you that a value is required.
- After the page loads, you should see the **item title** (if available) and how many images are on file.

---

## Working with multiple images

Some items have **more than one** photo (for example front, detail, or frame).

- Use the **Image** dropdown to switch between photos.
- Images marked **(primary)** in the list are the default the gallery chose in the system; you can still pick another.

---

## Scenes

The **Scene** dropdown lists presentation contexts (for example gallery wall vs residential interior). When suggestions load, you may also see **Presentation** hints (frame, lighting, placement) from the system.

**Current product note:** The MVP shows your selected **artwork image** clearly on screen and displays the **scene name** as context. **Room compositing** (blending the artwork into a generated room) is not applied yet; the page may show a **cache key** placeholder for a future compositor. The caption on the page explains this.

---

## When no images appear

If you see **“No images on file for this item”**:

- Pictures may not have been uploaded for that inventory record in Masterpiece.
- Add or activate images in the ERP, then **refresh** the showcase page.

---

## Privacy and sharing

- Only users with a valid **company login** and access to the widget can open showcase links.
- Treat preview links like internal tools: share them only with people who are allowed to see that inventory.

---

## Getting help

- If the page says showcase is **not enabled on the server**, contact your administrator (API configuration).
- If you are kicked to the **login** page, sign in again or ask IT to pass your session from the ERP (same flow as Module AI Insights).
- For wrong or missing pictures, work with inventory staff to correct **`company_item_pictures`** in Masterpiece.
