import React from "react";
import { UserRound } from "lucide-react";

// Reads an image file and returns a 160px square JPEG data URL, cropped from the center.
export function squareImage(file, size = 160) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      const side = Math.min(image.width, image.height);
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = size;
      canvas.getContext("2d").drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side, 0, 0, size, size);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", .86));
    };
    image.onerror = () => { URL.revokeObjectURL(url); reject(new Error("image")); };
    image.src = url;
  });
}
export function initials(user) {
  const text = (user?.display_name || user?.username || "").trim();
  if (!text || text.includes("@")) return "";
  const words = text.split(/\s+/);
  return ((words[0]?.[0] || "") + (words.length > 1 ? words.at(-1)[0] : "")).toUpperCase();
}
export function Avatar({ user, size = 32 }) {
  const picture = user?.avatar || "";
  const letters = initials(user);
  return <span className="avatar" style={{ "--avatar-size": size + "px" }} aria-hidden="true">
    {picture ? <img src={picture} alt="" /> : letters ? <b data-letters={letters} /> : <UserRound size={Math.round(size * .55)} />}
  </span>;
}
