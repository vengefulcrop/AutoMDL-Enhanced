# AutoMDL-Enhanced

This is a fork of the original [AutoMDL](https://github.com/NvC-DmN-CH/AutoMDL) addon, introducing a number of enhancements, like being able to compile multiple models from a single .blend file. It is meant primarily for compiling models from the same modular set (e.g., different wall pieces, variations of a prop) where core properties would typically be shared across all the pieces.

**Note:** This enhanced version should work, but it hasn't been tested thoroughly. If you find any bugs, please report them by opening an issue here. Tested using Portal 2 and Blender 4.3.2.

## Location

**`View3D > Sidebar > AutoMDL2`**

## Enhancements

*   **Collection-Based Compilation:** Instead of selecting individual visual and physics meshes, you now select a single Blender **Collection**. The addon will automatically:
    *   Find all valid visual mesh objects within the selected collection (ignoring objects starting with `COL_`).
    *   Look for a sub-collection named `COLLISION` (case-insensitive).
    *   Within the `COLLISION` sub-collection, find corresponding physics meshes named `COL_<VisMeshName>` (case-insensitive) for each visual mesh.
    *   Compile each visual mesh (with its optional physics mesh) into a separate `.mdl` file named after the visual mesh object.
*   **Automatic `$texturegroup` (Skins):** The addon automatically detects and generates `$texturegroup` QC commands for models with multiple skins based on a material naming convention:
    *   Name your base material normally (e.g., `Metal`).
    *   Name skin variants by appending `_skin<ID>` (e.g., `Metal_skin01`, `Metal_skin02`).
    *   The addon requires the base material (e.g., `Metal`) to also exist on the object for skins to be detected.
    *   Models using multiple base materials (e.g., `Metal`, `Wood`) can have skins. All materials ending in the same `_skin<ID>` (like `Metal_skin1` and `Wood_skin1`) will be grouped into the same skin family.
    *   Handles missing variants for specific skins - if an object has 2 or more base materials, but a certain skin does not have a corresponding material for one or the other, it will use the corresponding base material instead.

*   **Object Origin for Export:** Models are now exported relative to their own Blender object origin, rather than the world origin.
*   **Scale Factor:** A "QC Scale Factor" option has been added to the UI, allowing you to apply a `$scale` value during compilation directly from Blender (default is 100.0, for when you model in cm).
*   **Automatic Smooth Shading for Collision:** Collision meshes (found via `COL_<VisMeshName>`) will automatically have smooth shading applied if needed before export.
*   **Model Naming:** Compiled models (`.mdl`) use the name of the corresponding Blender *object*, not the name of the `.blend` file.
*   **Hidden objects** are skipped during export.

## Limitations

*   **Global Compile Options:** Several QC flags (`$staticprop`, `$mostlyopaque`, `$surfaceprop`) and the physics `mass` value are currently applied **globally** to *all* models compiled from the selected collection. They cannot be set individually per object within the collection via the UI.

## Known Issues

*   **First-Time Compile Error with Dots in Names:** If an object within the selected collection has a dot (`.`) in its name, the *first* time you compile the collection after launching Blender, it may result in an error for that specific object (often showing an empty Studiomdl error message). Compiling the collection again *without restarting Blender* will usually succeed. Renaming the object to remove the dot is the current workaround.

## Next steps

Ideally the plugin should be refactored to use TeamSpen's srctools lib or similar in the future, but no promises, I have no idea if I ever get to it. I may redo the game lookup at some point. 
