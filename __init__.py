bl_info = {
    "name": "AutoMDL-Enhanced",
    "author": "Vengefulcrop, NvC_DmN_CH",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > AutoMDL2",
    "description": "Compiles models for Source where the blend project file is, with some improvements.",
    "warning": "",
    "wiki_url": "https://github.com/vengefulcrop/AutoMDL-Enhanced/", 
    "category": "3D View"
}

import bpy
import os
import subprocess
import shutil
from pathlib import Path
import mathutils
import winreg
from bl_ui.generic_ui_list import draw_ui_list
import threading
from io import StringIO
import re
import glob # Import glob for file pattern matching
from typing import List, Dict, Tuple, Any, Set # Added typing imports
from collections import defaultdict

game_select_method_is_dropdown = None
temp_path = bpy.app.tempdir
games_paths_list = []
game_path = None
steam_path = None
studiomdl_path = None
gameManualTextGameinfoPath = None
gameManualTextInputIsInvalid = False
massTextInputIsInvalid = False
visMeshInputIsInvalid = False

def defineGameSelectDropdown(self, context):
    # game_select
    game_select_items_enum = []
    for i in range(len(games_paths_list)):
        game_name = str(os.path.basename(os.path.dirname(games_paths_list[i])))
        game_path = str(games_paths_list[i])
        item = (game_path, game_name, "")
        game_select_items_enum.append(item)
    
    
    bpy.types.Scene.game_select = bpy.props.EnumProperty(
        name = "Selected Option",
        items = game_select_items_enum,
        update = onGameDropdownChanged
    )

def onGameDropdownChanged(self, context):
    pass

def onMassTextInputChanged(self, context):
    global massTextInputIsInvalid
    massTextInputIsInvalid = not is_float(context.scene.mass_text_input)

def onGameManualTextInputChanged(self, context):
    global gameManualTextInputIsInvalid
    gameManualTextInputIsInvalid = False
    
    in_folder = str(Path(os.path.join(context.scene.studiomdl_manual_input, ''))) # make sure to have a trailing slash, and its a string
    subdir_studiomdl = os.path.join(in_folder, "studiomdl.exe")
    has_studiomdl = os.path.exists( subdir_studiomdl )
    if not has_studiomdl:
        gameManualTextInputIsInvalid = True
        print("ERROR: Couldn't find studiomdl.exe in specified folder")
        return
    
    base_path = Path(os.path.dirname(in_folder))
    gameinfo_path = None
    # oh no, code copy pasted from getGamesList()
    # anyway
    # 
    # although we need the path to the folder which contains the gameinfo
    # so we need to iterate now again
    _subdirectories = [x for x in base_path.iterdir() if x.is_dir()]
    for k in range(len(_subdirectories)):
        _subdir = _subdirectories[k]
        has_gameinfo = os.path.exists( os.path.join(_subdir, "gameinfo.txt") )
        
        # currently we're returning the first folder which has a gameinfo.txt, in alot of games there are multiple folders which match this criteria. todo: is this an issue?
        if( has_gameinfo ):
            gameinfo_path = str(_subdir)
            break
    
    if gameinfo_path == None:
        gameManualTextInputIsInvalid = True
        print("ERROR: Couldn't find gameinfo.txt in game")
        return
    
    gameManualTextGameinfoPath = gameinfo_path


def setGamePath(self, context, new_game_path_value):
    global game_path
    global studiomdl_path
    game_path = new_game_path_value
    studiomdl_path = os.path.join(os.path.dirname(game_path), "bin", "studiomdl.exe")

# returns list of source games which have a studiomdl.exe in the bin folder
def getGamesList():
    global steam_path
    common = Path(os.path.join(steam_path, r"steamapps/common"))
    
    # get all subdirectories in common
    subdirectories = [x for x in common.iterdir() if x.is_dir()]
    
    # okay let's filter games
    list = []
    
    for i in range(len(subdirectories)):
        subdir = subdirectories[i]
        subdir_bin = os.path.join(subdir, "bin")
        has_bin_folder = os.path.exists( subdir_bin )
        if( not has_bin_folder ):
            continue
        
        subdir_studiomdl = os.path.join(subdir_bin, "studiomdl.exe")
        has_studiomdl = os.path.exists( subdir_studiomdl )
        
        if( not has_studiomdl ):
            continue
        
        # okay!
        # although we need the path to the folder which contains the gameinfo
        # so we need to iterate now again
        _subdirectories = [x for x in subdir.iterdir() if x.is_dir()]
        for k in range(len(_subdirectories)):
            _subdir = _subdirectories[k]
            has_gameinfo = os.path.exists( os.path.join(_subdir, "gameinfo.txt") )
            
            # currently we're returning the first folder which has a gameinfo.txt, in alot of games there are multiple folders which match this criteria. todo: is this an issue?
            if( has_gameinfo ):
                list.append(_subdir)
                break
    
    return list

# attempt to figure out where steam is installed
def getSteamInstallationPath():
    
    # windows specific attempts
    if(os.name == 'nt'):
        # check in registry (x86)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam") as key:
                return winreg.QueryValueEx(key, "SteamPath")[0]
        except Exception as e:
            print(e)
        
        # check in registry (x64)
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
                return winreg.QueryValueEx(key, "InstallPath")[0]
        except Exception as e:
            print(e)
    
    # todo: linux specific attempts?
    
    return None


def refreshGameSelectDropdown(self, context):
    del bpy.types.Scene.game_select
    defineGameSelectDropdown(None, context)

# --- Helper Functions ---

def parse_material_skins(material_slots: list) -> Tuple[List[str], Dict[int, Dict[str, str]]]:
    """Parses material slots to identify base materials and their skin variants.

    Args:
        material_slots: A list of material slots from a Blender object.

    Returns:
        A tuple containing:
        - base_materials_ordered: An ordered list of base material names that have skins.
        - skin_groups: A dictionary mapping skin IDs (int) to dictionaries
                       where keys are base material names and values are the
                       corresponding skin variant names for that ID.
                       Example: {1: {'metal': 'metal_skin1', 'wood': 'wood_skin1'},
                                 2: {'metal': 'metal_skin2', 'wood': 'wood'}}
    """
    skin_pattern = re.compile(r"^(.*)_skin(\d+)$", re.IGNORECASE)
    base_candidates: Dict[str, Set[int]] = defaultdict(set) # base_name_lower: {skin_id}
    skin_variants: Dict[Tuple[str, int], str] = {} # (base_name_lower, skin_id): full_skin_name
    all_material_names: Set[str] = set() # Keep track of all original names

    for slot in material_slots:
        if slot.material:
            mat_name = slot.material.name
            all_material_names.add(mat_name)
            match = skin_pattern.match(mat_name)
            if match:
                base_name, skin_id_str = match.groups()
                skin_id = int(skin_id_str)
                base_name_lower = base_name.lower()
                base_candidates[base_name_lower].add(skin_id)
                skin_variants[(base_name_lower, skin_id)] = mat_name

    # Filter base candidates: only keep those whose base name actually exists as a material
    valid_base_materials_lower: Dict[str, Set[int]] = {}
    base_name_map_lower_to_original: Dict[str, str] = {}
    for base_lower, skin_ids in base_candidates.items():
        # Find the original casing for the base name
        original_base_name = next((name for name in all_material_names if name.lower() == base_lower), None)
        if original_base_name:
            valid_base_materials_lower[base_lower] = skin_ids
            base_name_map_lower_to_original[base_lower] = original_base_name

    if not valid_base_materials_lower:
        return [], {}

    # Determine the final ordered list of base materials (using original casing)
    base_materials_ordered: List[str] = sorted([base_name_map_lower_to_original[b] for b in valid_base_materials_lower.keys()])

    # Build the skin_groups dictionary
    skin_groups: Dict[int, Dict[str, str]] = defaultdict(dict)
    all_skin_ids = set(sid for ids in valid_base_materials_lower.values() for sid in ids)

    if not all_skin_ids:
        return [], {}

    min_skin_id = min(all_skin_ids)
    max_skin_id = max(all_skin_ids)

    for skin_id in range(min_skin_id, max_skin_id + 1):
        for base_name_original in base_materials_ordered:
            base_name_lower = base_name_original.lower()
            variant_key = (base_name_lower, skin_id)
            if variant_key in skin_variants:
                skin_groups[skin_id][base_name_original] = skin_variants[variant_key]
            else:
                # If no specific skin variant exists for this ID, use the base material name
                skin_groups[skin_id][base_name_original] = base_name_original

    # Filter out skin IDs that don't actually introduce any changes from the base
    final_skin_groups: Dict[int, Dict[str, str]] = {}
    base_row_dict = {base_name: base_name for base_name in base_materials_ordered}
    for skin_id, skin_map in skin_groups.items():
        if skin_map != base_row_dict:
            final_skin_groups[skin_id] = skin_map

    # Renumber skin IDs to be contiguous starting from 1 if necessary
    renumbered_skin_groups: Dict[int, Dict[str, str]] = {}
    if final_skin_groups:
        sorted_skin_ids = sorted(final_skin_groups.keys())
        for i, old_skin_id in enumerate(sorted_skin_ids):
            renumbered_skin_groups[i + 1] = final_skin_groups[old_skin_id]

    return base_materials_ordered, renumbered_skin_groups

def generate_texturegroup_qc(base_materials_ordered: List[str], skin_groups: Dict[int, Dict[str, str]]) -> str:
    """Generates the $texturegroup QC command string.

    Args:
        base_materials_ordered: An ordered list of base material names that have skins.
        skin_groups: A dictionary mapping *contiguous* skin IDs (starting from 1)
                     to dictionaries of {base_name: skin_variant_name}.

    Returns:
        The formatted $texturegroup QC string, or an empty string if no skins are defined.
    """
    if not base_materials_ordered or not skin_groups:
        return ""

    # Ensure skin_groups keys are contiguous and start from 1
    if not all(i + 1 in skin_groups for i in range(len(skin_groups))):
        print("Warning: Skin group IDs are not contiguous starting from 1. QC might be incorrect.")
        # Or raise an error, depending on desired strictness

    qc_string = "$texturegroup skinfamilies\n{\n"

    # Base materials line (Skin 0)
    base_line = "\t{ " + " ".join(f'"{mat}"' for mat in base_materials_ordered) + " }"
    qc_string += base_line + "\n"

    # Skin variant lines
    sorted_skin_ids = sorted(skin_groups.keys())
    for skin_id in sorted_skin_ids:
        skin_map = skin_groups[skin_id]
        skin_line = "\t{ "
        material_parts = []
        for base_name in base_materials_ordered:
            # Use the variant if present, otherwise default to the base name (should be handled by parse_material_skins)
            material_parts.append(f'"{skin_map.get(base_name, base_name)}"')
        skin_line += " ".join(material_parts) + " }"
        qc_string += skin_line + "\n"

    qc_string += "}\n"
    return qc_string


class AutoMDLOperator(bpy.types.Operator):
    bl_idname = "wm.automdl"
    bl_label = "Update MDL"
    bl_description = "Compile model"
    
    
    def execute(self, context):
        scn = context.scene

        # --- Preemptive Temp File Cleanup ---
        # self.report({'INFO'}, f"Cleaning temp directory: {temp_path}")
        # qc_pattern = os.path.join(temp_path, "qc_*.qc")
        # ref_smd_pattern = os.path.join(temp_path, "*_ref.smd")
        # phy_smd_pattern = os.path.join(temp_path, "*_phy.smd")
        # 
        # files_to_delete = glob.glob(qc_pattern) + glob.glob(ref_smd_pattern) + glob.glob(phy_smd_pattern)
        # 
        # deleted_count = 0
        # for f_path in files_to_delete:
        #     try:
        #         os.remove(f_path)
        #         deleted_count += 1
        #         # self.report({'INFO'}, f"Deleted old temp file: {os.path.basename(f_path)}") # Optional: Report each deleted file
        #     except OSError as e:
        #         self.report({'WARNING'}, f"Could not delete old temp file '{os.path.basename(f_path)}': {e}")
        # if deleted_count > 0:
        #      self.report({'INFO'}, f"Deleted {deleted_count} old temp files.")
        
        # --- Initial Setup & Validation ---
        if game_select_method_is_dropdown:
            if not scn.game_select:
                self.report({'ERROR'}, "Please select a game/compiler.")
                return {'CANCELLED'}
            setGamePath(self, context, scn.game_select)
        else:
            if not gameManualTextGameinfoPath:
                 self.report({'ERROR'}, "Manual game path is invalid or not set.")
                 return {'CANCELLED'}
            setGamePath(self, context, gameManualTextGameinfoPath)

        blend_path = bpy.data.filepath
        if not blend_path:
            self.report({'ERROR'}, "Please save the project file first.")
            return {'CANCELLED'}

        models_root = get_models_path(blend_path)
        if not models_root:
             self.report({'ERROR'}, "Please save the project inside a 'models' folder structure.")
             return {'CANCELLED'}
             
        selected_collection = scn.model_collection
        if not selected_collection:
            self.report({'ERROR'}, "Please select a Model Collection in the AutoMDL panel.")
            return {'CANCELLED'}
        
        # Calculate base relative path from blend file location ONCE
        try:
            relative_dir_path = os.path.relpath(os.path.dirname(blend_path), models_root).replace("\\", "/")
            if relative_dir_path == '.': # Handle case where blend is directly in models root
                relative_dir_path = ""
        except ValueError:
            self.report({'ERROR'}, "Blend file is not saved within the expected 'models' directory structure.")
            return {'CANCELLED'}

        # --- Global Compile Settings (Retrieve once) ---
        qc_staticprop = scn.staticprop
        qc_mass_str = scn.mass_text_input
        qc_surfaceprop = scn.surfaceprop
        qc_mostlyopaque = scn.mostlyopaque
        qc_scale_factor = scn.qc_scale_factor
        cdmaterials_type = scn.cdmaterials_type
        cdmaterials_list_manual = [item.name for item in scn.cdmaterials_list]
        make_folders = bpy.context.preferences.addons[__package__].preferences.do_make_folders_for_cdmaterials
        make_vmts = bpy.context.preferences.addons[__package__].preferences.do_make_vmts
        
        if not qc_staticprop and not is_float(qc_mass_str):
            self.report({'ERROR'}, "Mass value is invalid.")
            return {'CANCELLED'}
        qc_mass = float(qc_mass_str) if not qc_staticprop else 1 # Convert mass now
        
        # --- Find Collision Sub-Collection --- 
        collision_sub_collection = None
        for child in selected_collection.children:
            if child.name.lower() == "collision": # Case-insensitive check
                collision_sub_collection = child
                break

        # --- Process Each Object in Selected Collection ---
        mesh_ext = "smd" # SMD is currently the only supported format
        compiled_count = 0
        errors = []

        for obj in selected_collection.objects:
            # Filter for valid visual mesh objects AND check effective visibility
            if (obj.type != 'MESH' or               # Skip non-mesh objects
                obj.name.lower().startswith('col_') or # Skip collision meshes themselves
                obj.hide_get()):                   # Skip if hidden (considers hierarchy, layers etc.)
                continue # Skip this object and move to the next one

            # If we reach here, the object is a visible mesh not named like a collision mesh
            vis_mesh_obj = obj
            self.report({'INFO'}, f"Processing: {vis_mesh_obj.name}")

            # Sanitize name for filenames/paths
            vis_mesh_name_raw = vis_mesh_obj.name
            sanitized_vis_mesh_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in vis_mesh_name_raw)
            if not sanitized_vis_mesh_name:
                sanitized_vis_mesh_name = f"default_model_{compiled_count}" # Ensure unique fallback
                self.report({'WARNING'}, f"Visual mesh name '{vis_mesh_name_raw}' resulted in empty sanitized name. Using '{sanitized_vis_mesh_name}'.")

            # --- Determine Paths for this object ---
            qc_modelpath = os.path.join(relative_dir_path, sanitized_vis_mesh_name).replace("\\", "/") if relative_dir_path else sanitized_vis_mesh_name
            qc_vismesh_name = sanitized_vis_mesh_name + "_ref"
            qc_phymesh_name = sanitized_vis_mesh_name + "_phy"
            temp_qc_path = os.path.join(temp_path, f"qc_{sanitized_vis_mesh_name}.qc")
            temp_vis_smd_path = os.path.join(temp_path, qc_vismesh_name)
            temp_phy_smd_path = os.path.join(temp_path, qc_phymesh_name)
            
            # --- Find Corresponding Collision Mesh ---
            phy_mesh_obj = None
            has_collision = False
            if collision_sub_collection:
                expected_col_name = f"COL_{vis_mesh_obj.name}"
                for col_obj in collision_sub_collection.objects:
                    if col_obj.type == 'MESH' and col_obj.name.lower() == expected_col_name.lower():
                        phy_mesh_obj = col_obj
                        has_collision = True
                        # Check for smooth shading and apply if necessary
                        needs_smooth = any(not poly.use_smooth for poly in phy_mesh_obj.data.polygons)
                        if needs_smooth:
                            self.report({'INFO'}, f"Applying Shade Smooth to collision mesh '{phy_mesh_obj.name}' for '{vis_mesh_obj.name}'.")
                            try:
                                # Use foreach_set for potentially better performance
                                phy_mesh_obj.data.polygons.foreach_set("use_smooth", [True] * len(phy_mesh_obj.data.polygons))
                            except Exception as smooth_e:
                                self.report({'WARNING'}, f"Could not automatically apply Shade Smooth to '{phy_mesh_obj.name}': {smooth_e}. Skipping collision.")
                                phy_mesh_obj = None # Treat as no collision if smoothing fails
                                has_collision = False
                                
                        break # Found the matching collision mesh

            # --- Export SMDs ---
            try:
                self.exportObjectToSmd(vis_mesh_obj, temp_vis_smd_path, False)
                if has_collision:
                    self.exportObjectToSmd(phy_mesh_obj, temp_phy_smd_path, True)
            except Exception as e:
                error_msg = f"Failed to export SMD for '{vis_mesh_obj.name}': {e}"
                self.report({'ERROR'}, error_msg)
                errors.append(error_msg)
                continue # Skip this object

            # --- Parse Skin Materials ---
            base_materials_ordered, skin_groups = parse_material_skins(vis_mesh_obj.material_slots)

            # --- Prepare QC Data ---
            convex_pieces = 0
            if has_collision:
                try:
                    # Ensure collision mesh is up-to-date for island counting
                    depsgraph = context.evaluated_depsgraph_get()
                    phy_mesh_obj_eval = phy_mesh_obj.evaluated_get(depsgraph)
                    convex_pieces = CountIslands(phy_mesh_obj_eval)
                except Exception as e:
                     self.report({'WARNING'}, f"Could not count collision islands for '{phy_mesh_obj.name}': {e}. Proceeding without concave.")
                     convex_pieces = 1 # Assume single piece if count fails

            qc_cdmaterials_list_current = []
            has_materials = len(vis_mesh_obj.material_slots) > 0 and any(slot.material for slot in vis_mesh_obj.material_slots)

            if has_materials:
                if cdmaterials_type == '1': # Manual
                    qc_cdmaterials_list_current.extend([os.path.join(p, '', '').replace("\\", "/") for p in cdmaterials_list_manual])
                else: # Auto
                    # Auto path is relative to models/ directory, using the model's path
                    auto_cd_path = "models/" + os.path.dirname(qc_modelpath) if os.path.dirname(qc_modelpath) else "models"
                    qc_cdmaterials_list_current.append(auto_cd_path.replace("\\", "/"))

            qc_concave = convex_pieces > 1
            qc_maxconvexpieces = convex_pieces
            qc_inertia = 1
            qc_damping = 0
            qc_rotdamping = 0
            
            # --- Write QC File ---
            try:
                with open(temp_qc_path, "w") as file:
                    file.write(f'$modelname "{qc_modelpath}.mdl"\n')
                    if qc_scale_factor != 1.0:
                        file.write(f"$scale {qc_scale_factor:.6f}\n")
                    file.write("\n")
                    file.write(f'$bodygroup "Body"\n{{\n\tstudio "{qc_vismesh_name}.{mesh_ext}"\n}}\n')

                    # --- Write Texturegroup --- #
                    texturegroup_qc_string = generate_texturegroup_qc(base_materials_ordered, skin_groups)
                    if texturegroup_qc_string:
                        file.write("\n")
                        file.write(texturegroup_qc_string)

                    if qc_staticprop:
                        file.write("\n$staticprop\n")
                    if qc_mostlyopaque:
                        file.write("\n$mostlyopaque\n")
                    
                    file.write(f'\n$surfaceprop "{qc_surfaceprop}"\n')
                    file.write("\n$contents \"solid\"\n")
                    
                    file.write("\n")
                    if qc_cdmaterials_list_current:
                        for cd_path in qc_cdmaterials_list_current:
                            file.write(f'$cdmaterials "{cd_path}"\n')
                    else:
                         file.write('$cdmaterials ""\n') # Explicitly add if no materials/paths
                    
                    file.write("\n")
                    file.write(f'$sequence "idle" {{\n\t"{qc_vismesh_name}.{mesh_ext}"\n\tfps 30\n\tfadein 0.2\n\tfadeout 0.2\n\tloop\n}}\n')
                    
                    if has_collision:
                        file.write("\n")
                        collision_str = f'$collisionmodel "{qc_phymesh_name}.{mesh_ext}" {{'
                        if qc_concave:
                            collision_str += f"\n\t$concave\n\t$maxconvexpieces {qc_maxconvexpieces}"
                        collision_str += f"\n\t$mass {qc_mass}\n\t$inertia {qc_inertia}\n\t$damping {qc_damping}\n\t$rotdamping {qc_rotdamping}"
                        collision_str += '\n\t$rootbone " "' # Ensure rootbone exists
                        collision_str += "\n}}"
                        file.write(collision_str)
                        
            except IOError as e:
                error_msg = f"Failed to write QC file for '{vis_mesh_obj.name}': {e}"
                self.report({'ERROR'}, error_msg)
                errors.append(error_msg)
                # Attempt cleanup even if QC writing fails
                try:
                    if os.path.exists(temp_vis_smd_path + ".smd"): os.remove(temp_vis_smd_path + ".smd")
                    if os.path.exists(temp_phy_smd_path + ".smd"): os.remove(temp_phy_smd_path + ".smd")
                except OSError as clean_e:
                    self.report({'WARNING'}, f"Could not clean up temporary SMDs for '{vis_mesh_obj.name}' after QC error: {clean_e}")
                continue # Skip this object

            # --- Compile QC ---
            studiomdl_quiet = True
            studiomdl_fastbuild = False
            studiomdl_nowarnings = True
            studiomdl_nox360 = True
            studiomdl_args = [studiomdl_path, "-game", game_path, "-nop4"]
            if studiomdl_quiet: studiomdl_args.append("-quiet")
            if studiomdl_fastbuild: studiomdl_args.append("-fastbuild")
            if studiomdl_nowarnings: studiomdl_args.append("-nowarnings")
            if studiomdl_nox360: studiomdl_args.append("-nox360")
            studiomdl_args.append(temp_qc_path)
            
            try:
                # Use subprocess.run with check=True to catch compile errors based on exit code
                # Capture output to check for specific studiomdl errors if needed
                compile_result = subprocess.run(studiomdl_args, check=True, capture_output=True, text=True)
                # Optional: Log success or check output for warnings
                # print(f"Studiomdl output for {vis_mesh_obj.name}:\n{compile_result.stdout}")
            except subprocess.CalledProcessError as e:
                error_msg = f"Studiomdl failed for '{vis_mesh_obj.name}' (QC: {os.path.basename(temp_qc_path)}). Error:\n{e.stderr}"
                self.report({'ERROR'}, error_msg)
                errors.append(error_msg)
                # Attempt cleanup
                try:
                    if os.path.exists(temp_vis_smd_path + ".smd"): os.remove(temp_vis_smd_path + ".smd")
                    if os.path.exists(temp_phy_smd_path + ".smd"): os.remove(temp_phy_smd_path + ".smd")
                    if os.path.exists(temp_qc_path): os.remove(temp_qc_path)
                except OSError as clean_e:
                    self.report({'WARNING'}, f"Could not clean up temporary files for '{vis_mesh_obj.name}' after compile error: {clean_e}")
                continue # Skip this object
            except FileNotFoundError:
                error_msg = f"Studiomdl.exe not found at '{studiomdl_path}'. Cannot compile."
                self.report({'ERROR'}, error_msg)
                errors.append(error_msg)
                # No point continuing if studiomdl isn't found
                # Attempt cleanup for the current object
                try:
                     if os.path.exists(temp_vis_smd_path + ".smd"): os.remove(temp_vis_smd_path + ".smd")
                     if os.path.exists(temp_phy_smd_path + ".smd"): os.remove(temp_phy_smd_path + ".smd")
                     if os.path.exists(temp_qc_path): os.remove(temp_qc_path)
                except OSError as clean_e:
                    self.report({'WARNING'}, f"Could not clean up temporary files for '{vis_mesh_obj.name}' after studiomdl not found error: {clean_e}")
                break # Exit the loop
            
            # --- Create Material Folders/VMTs (for this object) ---
            if has_materials and make_folders:
                # Base path for materials, sibling to models folder
                materials_root = os.path.dirname(models_root)
                if materials_root: # Check if we could find the parent of 'models'
                    for cd_entry_rel in qc_cdmaterials_list_current:
                         # cd_entry_rel is like "models/props/myfolder" or a manual path
                         # We need the path relative to the *materials* folder
                         # If auto, it starts with models/, strip that. If manual, use as is?
                         # Let's assume manual paths are relative to materials/ already, 
                         # and auto paths need models/ stripped.
                         mat_rel_path = cd_entry_rel
                         if cd_entry_rel.startswith("models/"):
                             mat_rel_path = cd_entry_rel[len("models/"):]
                         elif cd_entry_rel.startswith("models\\"):
                             mat_rel_path = cd_entry_rel[len("models\\"):]
                             
                         mat_fullpath = Path(os.path.join(materials_root, "materials", mat_rel_path))
                         try:
                             os.makedirs(mat_fullpath, exist_ok=True)
                         except OSError as e:
                             print(f"Error creating material directory '{mat_fullpath}': {e}")
                             continue # Skip VMT creation if dir fails
                         
                         # Create placeholder VMTs if enabled AND using auto $cdmaterials
                         if make_vmts and cdmaterials_type == '0':
                             for slot in vis_mesh_obj.material_slots:
                                 if slot.material:
                                     mat_name = slot.material.name
                                     # Sanitize material name for filename? Maybe not needed for VMT.
                                     vmt_path = os.path.join(mat_fullpath, mat_name + '.vmt')
                                     if not os.path.exists(vmt_path):
                                         try:
                                             with open(vmt_path, "w") as file:
                                                 # Basetexture path assumes texture is in the same folder structure
                                                 vmt_basetexture = os.path.join(cd_entry_rel, mat_name).replace("\\", "/")
                                                 file.write(f'VertexLitGeneric\n{{\n\t$basetexture "{vmt_basetexture}"\n}}')
                                         except IOError as e:
                                             print(f"Error writing VMT file '{vmt_path}': {e}")
                else:
                    print("Could not determine parent directory of 'models' folder to create materials.")

            # --- Cleanup Temp Files for this object ---
            try:
                if os.path.exists(temp_vis_smd_path + ".smd"): os.remove(temp_vis_smd_path + ".smd")
                if os.path.exists(temp_phy_smd_path + ".smd"): os.remove(temp_phy_smd_path + ".smd")
                if os.path.exists(temp_qc_path): os.remove(temp_qc_path)
            except OSError as e:
                # Non-critical, just report
                self.report({'WARNING'}, f"Could not clean up temporary files for '{vis_mesh_obj.name}': {e}")

            compiled_count += 1
            self.report({'INFO'}, f"Finished processing: {vis_mesh_obj.name}")

        # --- Final Report ---
        if compiled_count > 0 and not errors:
            self.report({'INFO'}, f"Successfully compiled {compiled_count} model(s) from collection '{selected_collection.name}'. Output is in the blend file's directory.")
            return {'FINISHED'}
        elif compiled_count > 0 and errors:
            self.report({'WARNING'}, f"Compiled {compiled_count} model(s) from '{selected_collection.name}' with {len(errors)} error(s). Check console/report.")
            # Optionally print all errors here
            # for err in errors: print(err)
            return {'FINISHED'} # Still finished, but with warnings
        elif compiled_count == 0 and not errors:
             self.report({'WARNING'}, f"No valid visual mesh objects found in collection '{selected_collection.name}'. Nothing compiled.")
             return {'CANCELLED'}
        else: # No models compiled and errors occurred
             self.report({'ERROR'}, f"Failed to compile any models from '{selected_collection.name}'. {len(errors)} error(s) occurred. Check console/report.")
             # Optionally print all errors here
             # for err in errors: print(err)
             return {'CANCELLED'}

    
    def exportObjectToSmd(self, obj, path, is_collision_smd):
        
        # switch to object mode
        context_mode_snapshot = "OBJECT" # Default to object mode
        active_obj = bpy.context.active_object
        if active_obj and bpy.context.mode != 'OBJECT':
            context_mode_snapshot = active_obj.mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
        # Check if object exists and is a mesh
        if not obj or obj.name not in bpy.data.objects or obj.type != 'MESH':
             print(f"Error: Object '{obj.name if obj else 'None'}' not found or not a mesh.")
             # Switch mode back if changed
             if active_obj and bpy.context.mode != context_mode_snapshot:
                 bpy.ops.object.mode_set(mode=context_mode_snapshot)
             return # Indicate failure or handle error appropriately

        # Ensure UV layer exists
        if not obj.data.uv_layers:
             print(f"Warning: Object '{obj.name}' has no UV layers. Exporting with default UVs (0,0).")
             # Optionally create a default UV layer if needed, or just proceed
             # bpy.ops.mesh.uv_texture_add() # This would need object selection context

        # get mesh, apply modifiers
        depsgraph = bpy.context.evaluated_depsgraph_get()
        object_eval = obj.evaluated_get(depsgraph)
        try:
            mesh = object_eval.to_mesh()
        except RuntimeError as e:
            print(f"Error converting object '{obj.name}' to mesh: {e}")
            # Switch mode back if changed
            if active_obj and bpy.context.mode != context_mode_snapshot:
                bpy.ops.object.mode_set(mode=context_mode_snapshot)
            return
        # Ensure mesh is valid
        if not mesh:
             print(f"Error: Could not get mesh data for '{obj.name}' after evaluation.")
             # Switch mode back if changed
             if active_obj and bpy.context.mode != context_mode_snapshot:
                 bpy.ops.object.mode_set(mode=context_mode_snapshot)
             return

        mesh.calc_loop_triangles()

        # Apply object transform (rotation and scale only) to the mesh vertices
        loc, rot, scale = obj.matrix_world.decompose()
        mat_rot = rot.to_matrix().to_4x4()
        mat_sca = mathutils.Matrix.Diagonal(scale).to_4x4() # Simpler way to create scale matrix
        transform_matrix = mat_rot @ mat_sca # Apply scale then rotation
        mesh.transform(transform_matrix)

        # write!
        try:
            with open(path + ".smd", "w") as file:

                # hardcoded but yea
                file.write("version 1\nnodes\n0 \"root\" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\n")

                sb = StringIO() # string builder
                has_materials = len(obj.material_slots) > 0 and any(slot.material for slot in obj.material_slots)
                has_uvs = len(mesh.uv_layers) > 0

                # okay so now, i sacrifice everything that goes into making good code
                # just to squeeze out some performance of out this
                # because we REALLY do need the extra boost
                # no need to check for every triangle whether or not its a collision smd or presence of materials
                # so we check here and call the appropriate variant of the function
                if is_collision_smd:
                    self.exportMeshToSmd_Collision(sb, mesh, has_uvs) # Pass has_uvs flag
                else:
                    if has_materials:
                        self.exportMeshToSmd_WithMaterials(sb, obj, mesh, has_uvs) # Pass has_uvs flag
                    else:
                        self.exportMeshToSmd_NoMaterials(sb, mesh, has_uvs) # Pass has_uvs flag

                file.write(sb.getvalue())
                file.write("end\n")
        except IOError as e:
             print(f"Error writing SMD file {path}.smd: {e}")
        finally:
            # Clean up temporary mesh data
            if 'mesh' in locals() and mesh:
                object_eval.to_mesh_clear()

            # switch mode back
            if active_obj and bpy.context.mode != context_mode_snapshot:
                bpy.ops.object.mode_set(mode=context_mode_snapshot)
        
        
    def exportMeshToSmd_Collision(self, sb, mesh, has_uvs):
        active_uv_layer = mesh.uv_layers.active.data if has_uvs else None
        default_uv = mathutils.Vector((0.0, 0.0))

        for tri in mesh.loop_triangles:
            material_name = "Phy" # Collision meshes use a default material name

            # tri vertices
            vert_a = mesh.vertices[tri.vertices[0]]
            vert_b = mesh.vertices[tri.vertices[1]]
            vert_c = mesh.vertices[tri.vertices[2]]

            # tri positions
            pos_a = vert_a.co
            pos_b = vert_b.co
            pos_c = vert_c.co

            # tri normals (use vertex normals for collision)
            normal_a = vert_a.normal
            normal_b = vert_b.normal
            normal_c = vert_c.normal

            # tri uv coords (use default if no UVs)
            uv_a = active_uv_layer[tri.loops[0]].uv if has_uvs else default_uv
            uv_b = active_uv_layer[tri.loops[1]].uv if has_uvs else default_uv
            uv_c = active_uv_layer[tri.loops[2]].uv if has_uvs else default_uv

            # Use .format() for compatibility
            sb.write("{}\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n".format(
                material_name,
                pos_a.x, pos_a.y, pos_a.z, normal_a.x, normal_a.y, normal_a.z, uv_a.x, uv_a.y,
                pos_b.x, pos_b.y, pos_b.z, normal_b.x, normal_b.y, normal_b.z, uv_b.x, uv_b.y,
                pos_c.x, pos_c.y, pos_c.z, normal_c.x, normal_c.y, normal_c.z, uv_c.x, uv_c.y
            ))


    def exportMeshToSmd_WithMaterials(self, sb, obj, mesh, has_uvs):
        active_uv_layer = mesh.uv_layers.active.data if has_uvs else None
        default_uv = mathutils.Vector((0.0, 0.0))

        for tri in mesh.loop_triangles:
            material_name = "DefaultMaterial" # Default if slot is empty or index is wrong
            if tri.material_index < len(obj.material_slots) and obj.material_slots[tri.material_index].material:
                 material_name = obj.material_slots[tri.material_index].material.name
            # Sanitize material name (replace spaces, etc.) if needed for SMD compatibility
            # material_name = material_name.replace(" ", "_")

            # tri vertices
            vert_a = mesh.vertices[tri.vertices[0]]
            vert_b = mesh.vertices[tri.vertices[1]]
            vert_c = mesh.vertices[tri.vertices[2]]

            # tri positions
            pos_a = vert_a.co
            pos_b = vert_b.co
            pos_c = vert_c.co

            # tri normals
            normal_a = vert_a.normal
            normal_b = vert_b.normal
            normal_c = vert_c.normal

            # Use face normal if flat shaded
            if not tri.use_smooth:
                normal = tri.normal # Use pre-calculated loop triangle normal
                normal_a = normal
                normal_b = normal
                normal_c = normal

            # tri uv coords
            uv_a = active_uv_layer[tri.loops[0]].uv if has_uvs else default_uv
            uv_b = active_uv_layer[tri.loops[1]].uv if has_uvs else default_uv
            uv_c = active_uv_layer[tri.loops[2]].uv if has_uvs else default_uv

            # Use .format() for compatibility
            sb.write("{}\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n".format(
                material_name,
                pos_a.x, pos_a.y, pos_a.z, normal_a.x, normal_a.y, normal_a.z, uv_a.x, uv_a.y,
                pos_b.x, pos_b.y, pos_b.z, normal_b.x, normal_b.y, normal_b.z, uv_b.x, uv_b.y,
                pos_c.x, pos_c.y, pos_c.z, normal_c.x, normal_c.y, normal_c.z, uv_c.x, uv_c.y
            ))


    def exportMeshToSmd_NoMaterials(self, sb, mesh, has_uvs):
        active_uv_layer = mesh.uv_layers.active.data if has_uvs else None
        default_uv = mathutils.Vector((0.0, 0.0))

        for tri in mesh.loop_triangles:
            material_name = "DefaultMaterial" # Assign a default material name

            # tri vertices
            vert_a = mesh.vertices[tri.vertices[0]]
            vert_b = mesh.vertices[tri.vertices[1]]
            vert_c = mesh.vertices[tri.vertices[2]]

            # tri positions
            pos_a = vert_a.co
            pos_b = vert_b.co
            pos_c = vert_c.co

            # tri normals
            normal_a = vert_a.normal
            normal_b = vert_b.normal
            normal_c = vert_c.normal

            # Use face normal if flat shaded
            if not tri.use_smooth:
                normal = tri.normal # Use pre-calculated loop triangle normal
                normal_a = normal
                normal_b = normal
                normal_c = normal

            # tri uv coords
            uv_a = active_uv_layer[tri.loops[0]].uv if has_uvs else default_uv
            uv_b = active_uv_layer[tri.loops[1]].uv if has_uvs else default_uv
            uv_c = active_uv_layer[tri.loops[2]].uv if has_uvs else default_uv

            # Use .format() for compatibility
            sb.write("{}\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n0  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} {:.6f}  {:.6f} {:.6f} 0\n".format(
                material_name,
                pos_a.x, pos_a.y, pos_a.z, normal_a.x, normal_a.y, normal_a.z, uv_a.x, uv_a.y,
                pos_b.x, pos_b.y, pos_b.z, normal_b.x, normal_b.y, normal_b.z, uv_b.x, uv_b.y,
                pos_c.x, pos_c.y, pos_c.z, normal_c.x, normal_c.y, normal_c.z, uv_c.x, uv_c.y
            ))



class AutoMDLPanel(bpy.types.Panel):
    bl_label = "AutoMDL2"
    bl_idname = "PT_AutoMDLPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AutoMDL2'
    
    def draw(self, context):
        layout = self.layout
        scn = context.scene
        
        # Get the selected collection
        selected_collection = scn.model_collection
        collection_valid = selected_collection is not None
        
        row = layout.row()
        global steam_path
        if steam_path is not None:
            row.label(text= "Choose compiler:")
            row = layout.row()
            row.prop(scn, "game_select", text="")
        else:
            row.label(text= "Directory containing studiomdl.exe:")
            row = layout.row()
            row.alert = gameManualTextInputIsInvalid
            row.prop(scn, "studiomdl_manual_input")
            
        row = layout.row()
        
        # Operator button - Enabled only if a collection is selected
        row = layout.row()
        row.enabled = collection_valid
        row.operator("wm.automdl", text="Compile Collection") # Changed text for clarity
        row = layout.row()
        
        # Collection Selector
        row = layout.row()
        row.label(text= "Model Collection:")
        row.prop(scn, "model_collection", text="")
        
        row = layout.row()
        
        # Options dependent on having a valid collection selected
        # We keep Surfaceprop and Mass global for now as per the plan
        # These could eventually become per-object settings or derived
        box = layout.box()
        box.enabled = collection_valid # Enable/disable the whole box
        
        row = box.row()
        row.label(text= "Global Compile Options:")
        
        row = box.row()
        row.label(text= "Surface type:")
        row.prop(scn, "surfaceprop", text="")
                
        row = box.row()
        if not scn.staticprop:
            row.label(text= "Mass (per object):") # Clarify this is per-object mass
            row.alert = massTextInputIsInvalid
            row.prop(scn, "mass_text_input")
        else:
            row.label(text= "No mass (Static Prop)")

        # Removed concave UI - this will be determined automatically per collision mesh
        
        # $cdmaterials UI (remains global for now)
        row = box.row()
        row.label(text= "Path to VMT files will be:")
        row = box.row()
        row.prop(scn, 'cdmaterials_type', expand=True)
        row = box.row()
                
        if scn.cdmaterials_type == '0':
            row.label(text="Set automatically based on model path", icon='INFO')
            # Removed complex material path preview - less relevant for collections
        else:
            draw_ui_list(
                box, # Use the box layout
                context,
                list_path="scene.cdmaterials_list",
                active_index_path="scene.cdmaterials_list_active_index",
                unique_id="cdmaterials_list_id",
            )
                
        row = box.row()
        row.label(text="General options:")
        row = box.row()
        row.prop(scn, "mostlyopaque", text="Has Transparent Materials")
        
        row = box.row()
        row.prop(scn, "staticprop", text="Static Prop")

        # Scale UI
        row = box.row()
        row.prop(scn, "qc_scale_factor")


# for cdmaterials list

class CdMaterialsPropGroup(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()

class AddonPrefs(bpy.types.AddonPreferences):
    bl_idname = __package__
    
    do_make_folders_for_cdmaterials: bpy.props.BoolProperty(
        name="Make Folders",
        description="On compile, make the appropriate folders in the materials folder (make folders for each $cdmaterials)",
        default=True
    )
    
    do_make_vmts: bpy.props.BoolProperty(
        name="Make placeholder VMTs",
        description="On compile, make placeholder VMT files named after the model's materials, placed inside appropriate folder inside the materials folder\nThis won't replace existing VMTs",
        default=True
    )
    
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, "do_make_folders_for_cdmaterials", text="Automatically make folders for materials locations")
        row = layout.row()
        row.enabled = self.do_make_folders_for_cdmaterials
        row.prop(self, "do_make_vmts", text="Also make placeholder VMTs (Only when compiling with the \"Same as MDL\" option)")

classes = [
    AutoMDLOperator,
    AutoMDLPanel,
    CdMaterialsPropGroup,
    AddonPrefs
]

class_register, class_unregister = bpy.utils.register_classes_factory(classes)

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    
    # surfaceprop dropdown
    bpy.types.Scene.surfaceprop_text_input = bpy.props.StringProperty(name="", default="")
    
    # mass text input
    bpy.types.Scene.mass_text_input = bpy.props.StringProperty(name="", default="35", description="Mass in kilograms (KG)\nBy default, the Player can +USE pick up 35KG max.\nThe gravgun can pick up 250KG max.\nThe portal gun can pick up 85KG max", update=onMassTextInputChanged)
    
    # Model Collection Selector
    bpy.types.Scene.model_collection = bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name="Model Collection",
        description="Select the collection containing models to compile"
    )
    
    # surfaceprop
    bpy.types.Scene.surfaceprop = bpy.props.EnumProperty(
        name="Selected Option",
        items = [
            ("Concrete", "Concrete", ""),
            ("Chainlink", "Chainlink", ""),
            ("Canister", "Canister", ""),
            ("Crowbar", "Crowbar", ""),
            ("Metal", "Metal", ""),
            ("Metalvent", "Metalvent", ""),
            ("Popcan", "Popcan", ""),
            ("Wood", "Wood", ""),
            ("Plaster", "Plaster", ""),
            ("Dirt", "Dirt", ""),
            ("Grass", "Grass", ""),
            ("Sand", "Sand", ""),
            ("Snow", "Snow", ""),
            ("Ice", "Ice", ""),
            ("Flesh", "Flesh", ""),
            ("Glass", "Glass", ""),
            ("Tile", "Tile", ""),
            ("Paper", "Paper", ""),
            ("Cardboard", "Cardboard", ""),
            ("Plastic_Box", "Plastic_Box", ""),
            ("Plastic_barrel", "Plastic_barrel", ""),
            ("Plastic", "Plastic", ""),
            ("Rubber", "Rubber", ""),
            ("Clay", "Clay", ""),
            ("Porcelain", "Porcelain", ""),
            ("Computer", "Computer", "")
        ]
    )
    
    # static prop
    bpy.types.Scene.staticprop = bpy.props.BoolProperty(
        name="Static Prop",
        description="Enable if used as prop_static\n($staticprop in QC)",
        default=False
    )
    
    # has transparency
    bpy.types.Scene.mostlyopaque = bpy.props.BoolProperty(
        name="Has Transparency",
        description="Enabling this may fix sorting issues that come with using transparent materials. \nRenders model in 2 passes, one for opaque materials, and one for materials with transparency\n($mostlyopaque in QC)",
        default=False
    )
    
    # *** RENAME and UPDATE SCALE PROPERTY ***
    bpy.types.Scene.qc_scale_factor = bpy.props.FloatProperty(
        name="QC Scale Factor",
        description="Model scale factor ($scale value in QC, 1.0 = normal size)",
        default=100.0,
        min=0.0, # Scale can be zero or positive
        precision=6 # Allow fine control over scale
    )
    
    # radio buttons for choosing how to define cdmaterials
    bpy.types.Scene.cdmaterials_type = bpy.props.EnumProperty(items =
        (
            ('0','Same as MDL',''),
            ('1','Other','')
        )
    )
    
    # cdmaterials list
    bpy.types.Scene.cdmaterials_list = bpy.props.CollectionProperty(type=CdMaterialsPropGroup)
    bpy.types.Scene.cdmaterials_list_active_index = bpy.props.IntProperty()
    
    # steam path
    global steam_path
    global games_paths_list
    global game_select_method_is_dropdown
    steam_path = getSteamInstallationPath()
    if(steam_path != None):
        game_select_method_is_dropdown = True
        steam_path = os.path.join(steam_path, "").replace("\\", "/")
        games_paths_list = getGamesList()
        defineGameSelectDropdown(None, bpy.context)
    else:
        game_select_method_is_dropdown = False
        steam_path = None
        bpy.types.Scene.studiomdl_manual_input = bpy.props.StringProperty(name="", default="", description="Path to the studiomdl.exe file", update=onGameManualTextInputChanged)
        
    
    # call something after 1 second
    bpy.app.timers.register(set_default_values, first_interval=1) # workaround for not being able to use context in register()

def set_default_values():
    # set default of cdmaterials list
    bpy.context.scene.cdmaterials_list.clear()
    bpy.ops.uilist.entry_add(list_path="scene.cdmaterials_list", active_index_path="scene.cdmaterials_list_active_index")
    bpy.context.scene.cdmaterials_list[0].name = "models/"
    
    # we need to update the dropdown once to let the default value affect the rest of the program, as if we selected it manually
    # before that let's select a default value for it
    global game_select_method_is_dropdown
    if game_select_method_is_dropdown:
        
        # if certain games exist, select one of them instead of defaulting to selecting the game in the first option
        chosen_game_path = None
        recognized_game_path_gmod = None
        recognized_game_path_hl2 = None
        recognized_game_path_sdk = None
        
        global games_paths_list
        for i in range(len(games_paths_list)):
            game_path = str(games_paths_list[i])
            game_path_lowercase = game_path.lower()
            
            # we're not checking for specific strings because from what i saw the names of the games aren't consistent across users
            # like idk, i remember seeing "Half Life 2" as "Half-Life 2" and "Half Life: 2" which is weird but idk
            # i may be wrong but, we do this for now and im actually happy with it
            # 
            # checking smaller strings first for optimization (but not if its gonna be a very common string)
            
            if "mod" in game_path_lowercase:
                if "s" in game_path_lowercase:
                    if "garry" in game_path_lowercase:
                        # we are gonna assume its "GarrysMod" or something like that
                        recognized_game_path_gmod = game_path
                        continue
            
            if "2" in game_path_lowercase:
                if "half" in game_path_lowercase:
                    if "life" in game_path_lowercase:
                        # we are gonna assume its "Half-Life 2" or something like that (episodes, lost coast etc)
                        recognized_game_path_hl2 = game_path
                        continue
            
            if "sdk" in game_path_lowercase:
                if "2013" in game_path_lowercase:
                    # we are gonna assume its "Source SDK Base 2013 Singleplayer" or something like that
                    recognized_game_path_sdk = game_path
                    continue
        
        # lets now define some sort of order so that we prefer some recognized games over others
        # sdk > hl2 > gmod
        if recognized_game_path_sdk is not None:
            chosen_game_path = recognized_game_path_sdk
        elif recognized_game_path_hl2 is not None:
            chosen_game_path = recognized_game_path_hl2
        elif recognized_game_path_gmod is not None:
            chosen_game_path = recognized_game_path_gmod   
        
        # set value
        if chosen_game_path != None:
            bpy.context.scene.game_select = chosen_game_path
        
        # update once to set up things ( i removed functionality there so not needed anymore )
        onGameDropdownChanged(None, bpy.context)
    else:
        # update once to set up things
        onGameManualTextInputChanged(None, bpy.context)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    
    del bpy.types.Scene.surfaceprop_text_input
    del bpy.types.Scene.model_collection
    del bpy.types.Scene.surfaceprop
    del bpy.types.Scene.staticprop
    del bpy.types.Scene.mass_text_input
    del bpy.types.Scene.qc_scale_factor # Update cleanup for scale property
    
    if game_select_method_is_dropdown:
        del bpy.types.Scene.game_select
    else:
        del bpy.types.Scene.studiomdl_manual_input
    
    del bpy.types.Scene.cdmaterials_type
    
    del bpy.types.Scene.cdmaterials_list
    del bpy.types.Scene.cdmaterials_list_active_index


def checkVisMeshHasMesh(context):
    vis_mesh_obj = context.scene.vis_mesh
    return (vis_mesh_obj and vis_mesh_obj.type == 'MESH' and vis_mesh_obj.name in bpy.data.objects) == True


def checkPhyMeshHasMesh(context):
    phy_mesh_obj = context.scene.phy_mesh
    return (phy_mesh_obj and phy_mesh_obj.type == 'MESH' and phy_mesh_obj.name in bpy.data.objects) == True


def to_models_relative_path(file_path):
    MODELS_FOLDER_NAME = "models"

    
    # See if we can find a models folder up the chain
    index = file_path.rfind(MODELS_FOLDER_NAME)

    if index != -1:
        root = file_path[:index + len(MODELS_FOLDER_NAME)]
    else:
        return None

    return os.path.splitext(os.path.relpath(file_path, root))[0].replace("\\", "/")

def get_models_path(file_path):
    MODELS_FOLDER_NAME = "models"

    
    # See if we can find a models folder up the chain
    index = file_path.rfind(MODELS_FOLDER_NAME)

    if index != -1:
        root = file_path[:index + len(MODELS_FOLDER_NAME)]
        return root
    
    return None




# lemon's answer in https://blender.stackexchange.com/questions/75332/how-to-find-the-number-of-loose-parts-with-blenders-python-api

# i would implement it myself but i haven't done much graph stuff, and speed is really needed right now, and first implementation would be slow. This here is an efficient alogrithm to count the number of loose parts inside a mesh

from collections import defaultdict

def MakeVertPaths( verts, edges ):
    #Initialize the path with all vertices indexes
    result = {v.index: set() for v in verts}
    #Add the possible paths via edges
    for e in edges:
        result[e.vertices[0]].add(e.vertices[1])
        result[e.vertices[1]].add(e.vertices[0])
    return result

def FollowEdges( startingIndex, paths ):
    current = [startingIndex]

    follow = True
    while follow:
        #Get indexes that are still in the paths
        eligible = set( [ind for ind in current if ind in paths] )
        if len( eligible ) == 0:
            follow = False #Stops if no more
        else:
            #Get the corresponding links
            next = [paths[i] for i in eligible]
            #Remove the previous from the paths
            for key in eligible: paths.pop( key )
            #Get the new links as new inputs
            current = set( [ind for sub in next for ind in sub] )

def CountIslands( obj ):
    #Prepare the paths/links from each vertex to others
    paths = MakeVertPaths( obj.data.vertices, obj.data.edges )
    found = True
    n = 0
    while found:
        try:
            #Get one input as long there is one
            startingIndex = next( iter( paths.keys() ) )
            n = n + 1
            #Deplete the paths dictionary following this starting index
            FollowEdges( startingIndex, paths )               
        except:
            found = False
    return n


def CountIslands2(obj):
    mesh = obj.data
    paths={v.index:set() for v in mesh.vertices}
    for e in mesh.edges:
        paths[e.vertices[0]].add(e.vertices[1])
        paths[e.vertices[1]].add(e.vertices[0])
    lparts=[]
    while True:
        try:
            i=next(iter(paths.keys()))
        except StopIteration:
            break
        lpart={i}
        cur={i}
        while True:
            eligible={sc for sc in cur if sc in paths}
            if not eligible:
                break
            cur={ve for sc in eligible for ve in paths[sc]}
            lpart.update(cur)
            for key in eligible: paths.pop(key)
        lparts.append(lpart)
    
    return len(lparts)


def is_float(value):
  if value is None:
      return False
  try:
      float(value)
      return True
  except:
      return False


if __name__ == "__main__":
    register()
