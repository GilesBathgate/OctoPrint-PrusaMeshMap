# coding=utf-8
from __future__ import absolute_import

import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import re
import octoprint.plugin
import octoprint.printer

class PrusameshmapPlugin(octoprint.plugin.SettingsPlugin,
                         octoprint.plugin.AssetPlugin,
                         octoprint.plugin.TemplatePlugin,
                         octoprint.plugin.StartupPlugin):

	##~~ SettingsPlugin mixin
	def get_settings_defaults(self):
		return dict(
                        do_level_gcode = 'G28 W ; home all without mesh bed level\nG80 ; mesh bed leveling\nG81 ; check mesh leveling results',
                        matplotlib_heightmap_theme = 'inferno',
                        dark_theme = True
		)

	##~~ AssetPlugin mixin
	def get_assets(self):
		return dict(
			js=["js/PrusaMeshMap.js"],
			css=["css/PrusaMeshMap.css"],
			less=["less/PrusaMeshMap.less"],
                        img_heightmap=["img/heightmap.png"]
		)
        ##~~ TemplatePlugin mixin
        def get_template_configs(self):
            return [
                    dict(type="tab", template="PrusaMeshMap_tab.jinja2", name="Bed")
            ]

	##~~ Softwareupdate hook
	def get_update_information(self):
		return dict(
			PrusaMeshMap=dict(
				displayName="Prusameshmap Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="GilesBathgate",
				repo="OctoPrint-PrusaMeshMap",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/GilesBathgate/OctoPrint-PrusaMeshMap/archive/{target_version}.zip"
			)
		)

        ##~~ GCode Received hook
        def mesh_level_check(self, comm, line, *args, **kwargs):
                if re.match(r"^(  -?\d+.\d+)+$", line):
                    self.mesh_level_responses.append(line)
                    self._logger.info("FOUND: " + line)
                    self.mesh_level_generate()
                    return line
                else:
                    return line

        ##~~ Mesh Bed Level Heightmap Generation
        def zeros_1d(self,n):
            return [0 for i in range(n)]

        def zeros_2d(self,n,m):
            return [[0] * m for i in range(n)]

        def max(self,mesh):
            max_z = -float("inf")
            for col in mesh:
                for row in col:
                    max_z = row if row > max_z else max_z
            return max_z

        def min(self,mesh):
            min_z = float("inf")
            for col in mesh:
                for row in col:
                    min_z = row if row < min_z else min_z
            return min_z

        mesh_level_responses = []

        def mesh_level_generate(self):

            # We work with coordinates relative to the dashed line on the
            # skilkscreen on the MK52 heatbed: print area coordinates. Note
            # this doesn't exactly line up with the steel sheet, so we have to
            # adjust for that when generating the background image, below.
            # Points are measured from the middle of the PINDA / middle of the
            # 4 probe circles on the MK52.

            MESH_NUM_POINTS_X = 7
            MESH_NUM_MEASURED_POINTS_X = 3
            MESH_NUM_POINTS_Y = 7
            MESH_NUM_MEASURED_POINTS_Y = 3
            BED_SIZE_X = 250
            BED_SIZE_Y = 210

            # These values come from mesh_bed_calibration.cpp
            BED_PRINT_ZERO_REF_X = 2
            BED_PRINT_ZERO_REF_Y = 9.4

            # Mesh probe points, in print area coordinates
            # We assume points are symmetrical (i.e a rectangular grid)
            MESH_FRONT_LEFT_X = 37 - BED_PRINT_ZERO_REF_X
            MESH_FRONT_LEFT_Y = 18.4 - BED_PRINT_ZERO_REF_Y

            MESH_REAR_RIGHT_X = 245 - BED_PRINT_ZERO_REF_X
            MESH_REAR_RIGHT_Y = 210.4 - BED_PRINT_ZERO_REF_Y

            # Offset of the marked print area on the steel sheet relative to
            # the marked print area on the MK52. The steel sheet has margins
            # outside of the print area, so we need to account for that too.

            SHEET_OFFS_X = 0
            # Technically SHEET_OFFS_Y is -2 (sheet is BELOW (frontward to) that on the MK52)
            # However, we want to show the user a view that looks lined up with the MK52, so we
            # ignore this and set the value to zero.
            SHEET_OFFS_Y = 0
                               # 
            SHEET_MARGIN_LEFT = 0
            SHEET_MARGIN_RIGHT = 0
            # The SVG of the steel sheet (up on Github) is not symmetric as the actual one is
            SHEET_MARGIN_FRONT = 17
            SHEET_MARGIN_BACK = 14

            sheet_left_x = -(SHEET_MARGIN_LEFT + SHEET_OFFS_X)
            sheet_right_x = sheet_left_x + BED_SIZE_X + SHEET_MARGIN_LEFT + SHEET_MARGIN_RIGHT
            sheet_front_y = -(SHEET_MARGIN_FRONT + SHEET_OFFS_Y)
            sheet_back_y = sheet_front_y + BED_SIZE_Y + SHEET_MARGIN_FRONT + SHEET_MARGIN_BACK


            mesh_range_x = MESH_REAR_RIGHT_X - MESH_FRONT_LEFT_X
            mesh_range_y = MESH_REAR_RIGHT_Y - MESH_FRONT_LEFT_Y

            mesh_delta_x = mesh_range_x / (MESH_NUM_POINTS_X - 1)
            mesh_delta_y = mesh_range_y / (MESH_NUM_POINTS_Y - 1)

            # Accumulate response lines until we have all of them
            if len(self.mesh_level_responses) == MESH_NUM_POINTS_Y:

                self._logger.info("Generating heightmap")

                # TODO: Validate each row has MESH_NUM_POINTS_X values

                mesh_values = []

                # Parse response lines into a 2D array of floats in row-major order
                for response in self.mesh_level_responses:
                    response = re.sub(r"^[ ]+", "", response)
                    response = re.sub(r"[ ]+", ",", response)
                    mesh_values.append([float(i) for i in response.split(",")])

                # Generate a 2D array of the Z values in column-major order
                center_z = mesh_values[3][3]
                col_i = 0
                mesh_z = self.zeros_2d(7,7)
                for col in mesh_values:
                    row_i = 0
                    for val in col:
                        mesh_z[col_i][row_i] = (val - center_z)
                        row_i = row_i + 1
                    col_i = col_i + 1

                # Calculate the X and Y values of the mesh bed points, in print area coordinates
                mesh_x = self.zeros_1d(MESH_NUM_POINTS_X)
                for i in range(0, MESH_NUM_POINTS_X):
                    mesh_x[i] = MESH_FRONT_LEFT_X + mesh_delta_x*i

                mesh_y = self.zeros_1d(MESH_NUM_POINTS_Y)
                for i in range(0, MESH_NUM_POINTS_Y):
                    mesh_y[i] = MESH_FRONT_LEFT_Y + mesh_delta_y*i

                bed_variance = round(self.max(mesh_z) - self.min(mesh_z), 3)

                ############
                # Draw the heightmap
                dark_theme = self._settings.get_boolean(["dark_theme"])
                if dark_theme:
                    plt.style.use('dark_background')
                else:
                    plt.style.use('classic')

                fig = plt.figure(dpi=96, figsize=(10,8.3))
                ax = plt.gca()

                # Plot all mesh points, including measured ones and the ones
                # that are bogus (calculated). Indicate the actual measured
                # points with a different marker.
                for x_i in range(0, len(mesh_x)):
                    for y_i in range(0, len(mesh_y)):
                        if ((x_i % MESH_NUM_MEASURED_POINTS_X) == 0) and ((y_i % MESH_NUM_MEASURED_POINTS_Y) == 0):
                            plt.plot(mesh_x[x_i], mesh_y[y_i], 'o', color='m')
                        else:
                            plt.plot(mesh_x[x_i], mesh_y[y_i], '.', color='k')

                # Draw the contour map. Y values are reversed to account for
                # bottom-up orientation of plot library
                contour = plt.contourf(mesh_x, mesh_y[::-1], mesh_z, alpha=.75, antialiased=True, cmap=plt.cm.get_cmap(self._settings.get(["matplotlib_heightmap_theme"])))

                # Insert the background image (currently an image of the MK3 PEI-coated steel sheet)
                if dark_theme:
                   img = mpimg.imread(self.get_asset_folder() + '/img/mk52_steel_sheet_dark.png')
                else:
                   img = mpimg.imread(self.get_asset_folder() + '/img/mk52_steel_sheet.png')

                plt.imshow(img, extent=[sheet_left_x, sheet_right_x, sheet_front_y, sheet_back_y], interpolation="lanczos", cmap=plt.cm.get_cmap(self._settings.get(["matplotlib_heightmap_theme"])))

                # Set axis ranges (although we don't currently show these...)
                ax.set_xlim(left=sheet_left_x, right=sheet_right_x)
                ax.set_ylim(bottom=sheet_front_y, top=sheet_back_y)

                # Set various options about the graph image before
                # we generate it. Things like labeling the axes and
                # colorbar, and setting the X axis label/ticks to
                # the top to better match the G81 output.
                plt.title("Mesh Level: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                plt.axis('image')
                #ax.axes.get_xaxis().set_visible(True)
                #ax.axes.get_yaxis().set_visible(True)
                plt.xlabel("X Axis (mm)")
                plt.ylabel("Y Axis (mm)")

                #plt.colorbar(label="Bed Variance: " + str(round(mesh_z.max() - mesh_z.min(), 3)) + "mm")
                plt.colorbar(contour, label="Measured Level (mm)")

                box = dict(facecolor='#eeefff', alpha=0.5)

                plt.text(0.08, 0.90, "{:.2f}".format(mesh_z[0][0]), fontsize=10, horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, bbox=box)
                plt.text(0.90, 0.90, "{:.2f}".format(mesh_z[0][6]), fontsize=10, horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, bbox=box)
                plt.text(0.08, 0.15, "{:.2f}".format(mesh_z[6][0]), fontsize=10, horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, bbox=box)
                plt.text(0.90, 0.15, "{:.2f}".format(mesh_z[6][6]), fontsize=10, horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, bbox=box)

                plt.text(0.5 , 0.49, "{:.2f}".format(mesh_z[3][3]), fontsize=10, horizontalalignment='center', verticalalignment='center', transform=ax.transAxes, bbox=box)
                
                plt.text(0.5, 0.05, "Total Bed Variance: " + str(bed_variance) + " (mm)", fontsize=10, horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)

                # Save our graph as an image in the current directory.
                fig.savefig(self.get_asset_folder() + '/img/heightmap.png', bbox_inches="tight", transparent=True)
                self._logger.info("Heightmap updated")

                del self.mesh_level_responses[:]


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "Prusa Mesh Leveling"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = PrusameshmapPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
                "octoprint.comm.protocol.gcode.received": __plugin_implementation__.mesh_level_check
	}

