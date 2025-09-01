import bpy
import os
import csv
import subprocess
from datetime import datetime
from datetime import timedelta

def draw_render_progress(self, context):
	layout = self.layout
	layout.separator()
	layout.label(text = f"{render_type} Render")
	row = layout.row(align=True)
	row.progress(factor = context.scene.render_progress, text = str(int(context.scene.render_progress*100)) + '%')
	row.prop(context.scene, 'cancel_key_render', text = '', icon = 'X')
	if len(render_avg_time) > 0:
		render_avg_time_seconds = [td.total_seconds() for td in render_avg_time]
		average = sum(render_avg_time_seconds) / len(render_avg_time_seconds)
		layout.separator()
		layout.label(text = f'Avg time: {str(timedelta(seconds=average))[:-4]}  Remaining time: {str(timedelta(seconds=average*range_total*(1 - context.scene.render_progress)))[:-4]}')

def get_keyed(self, context):
	keyed = []
	start = context.scene.frame_start
	end = context.scene.frame_end
	markers = context.scene.timeline_markers

	render_visible_set = []
	depsgraph = context.evaluated_depsgraph_get()
	for object_instance in depsgraph.object_instances:
		o = object_instance.object
		render_visible_set.append(o.name_full)

	for marker in markers:
		keyed.append(marker.frame)
		
	for obj in context.scene.objects:
		if obj.name_full in render_visible_set:
			if obj.animation_data and obj.animation_data.action:
				slot = obj.animation_data.action_slot
				if slot:
					for fcurve in obj.animation_data.action.layers[0].strips[0].channelbag(slot).fcurves:
						for keyframe_point in fcurve.keyframe_points:
							x, y = keyframe_point.co
							if x >= start and x <= end and x not in keyed:
								keyed.append(int(x))

	keyed.append(start)
	keyed.append(end)

	keyed = list(set(keyed))
	keyed = sorted(keyed)

	return keyed

def get_format(item):
	format = item.file_format
	if format == 'OPEN_EXR_MULTILAYER' or format == 'OPEN_EXR':
		file_format = '.exr'
	elif format == 'PNG':
		file_format = '.png'
	elif format == 'JEPG' or format == 'JEPG2000':
		file_format = '.jpg'
	elif format == 'BMP':
		file_format = '.bmp'
	else:
		file_format = ''

	return file_format

def rename_render(self, directory, filename, format):
	for i, queue in enumerate(self.full_queue):
		if self.use_range and (queue < self.range_start or queue > self.range_end):
			continue
				
		rendername = filename + "%04d" % queue + get_format(format)
		oredername = filename + "_" + "%04d" % i + get_format(format)

		render_path = os.path.join(directory, rendername)
		oreder_path = os.path.join(directory, oredername)

		if os.path.exists(oreder_path) and os.path.exists(render_path):
			os.remove(oreder_path)

		if os.path.exists(render_path):
			os.rename(render_path, oreder_path)

def reorder_render_name(self, context):
	scene = context.scene
	if context.scene.use_nodes == True and any(node.type == 'OUTPUT_FILE' for node in context.scene.node_tree.nodes):
		for node in scene.node_tree.nodes:
			if node.type == 'OUTPUT_FILE':
				directory, filename = os.path.split(node.base_path)
				rename_render(self, directory, filename, node.format)
	else:
		directory, filename = os.path.split(context.scene.render.filepath)
		image_settings = context.scene.render.image_settings
		rename_render(self, directory, filename, image_settings)

def index_to_alphabetic(index):
    result = ""
    while index >= 0:
        result = chr(index % 26 + 65) + result
        index = index // 26 - 1
        if index < 0:
            break
    return result

def export_csv(self, context):
	scene = context.scene
	frameRate = scene.render.fps
	frame_end = scene.frame_end
	frame_count = frame_end + 1
	header = []
	if context.scene.use_nodes == True and any(node.type == 'OUTPUT_FILE' for node in context.scene.node_tree.nodes):
		for node in scene.node_tree.nodes:
			if node.type == 'OUTPUT_FILE':
				header.append(os.path.basename(os.path.dirname(node.base_path)))
	else:
		header.append(os.path.split(context.scene.render.filepath)[1])

	header_data = ['']
	for i, header in enumerate(header):
		if self.csv_header == 'Name':
			header_data.append(header)
		elif self.csv_header == 'Letters':
			header_data.append(index_to_alphabetic(i))

	frame_data = []
	for i in range(frame_count):
		frame_data.append([])
		for j in range(len(header_data)+1):
			frame_data[i].append('')

	for i in range(frame_count):
		frame_data[i][0] = i
		
	for frame_index, frame in enumerate(self.full_queue):
		if frame in range(frame_count):
			for layer_index, header_value in enumerate(header_data[:-1]):
				frame_data[frame][layer_index + 1] = frame_index

	directory, filename = os.path.split(context.scene.render.filepath)
	csvfile = os.path.join(directory, filename + "_Timesheet" + '.csv')

	with open(csvfile, 'w', encoding='gbk', errors='replace', newline='') as f:
		writer = csv.writer(f)
		writer.writerow(['Frame', 'Action', f'FPS {frameRate}'])
		writer.writerow(header_data)
		for row in frame_data:
			writer.writerow(row)

class RENDER_OT_Keyed(bpy.types.Operator):
	bl_idname = "render.keyed"
	bl_label = "Keyed Render"
	bl_options = {'REGISTER', 'UNDO'}

	full_queue = None
	rendering = None
	render_queue = None
	timer_event = None
	i = 0
	directory = None
	filename = None
	current_frame_list = None
	original_frame = None
	output_path = None
	
	background: bpy.props.BoolProperty(options={'HIDDEN'}, default=False)
	kill: bpy.props.BoolProperty(options={'HIDDEN'}, default=False)

	use_range: bpy.props.BoolProperty(name = 'Use Range',default=False)
	range_start: bpy.props.IntProperty(name = 'Start',default=0)
	range_end: bpy.props.IntProperty(name = 'End',default=0)

	export_csv: bpy.props.BoolProperty(name = 'Export CSV',default=True)

	csv_header : bpy.props.EnumProperty(
		name = "CSV Header Type",
		default='Name',
		items=[('Name', 'Name', ''),
				('Letters', 'Letters', ''),
				])

	def invoke(self, context, event):
		if self.range_start == 0:
			self.range_start = context.scene.frame_start
		if self.range_end == 0:
			self.range_end = context.scene.frame_end
		return context.window_manager.invoke_props_dialog(self, width=300)
	
	def draw(self, context):
		layout = self.layout
		layout.use_property_split = True

		col = layout.column()
		col.prop(self,'use_range')
		sub = col.column(align=True)
		sub.active = self.use_range
		sub.prop(self,'range_start')
		sub.prop(self,'range_end')

		col = layout.column()
		col.prop(self,'export_csv')
		if self.export_csv:
			col.row().prop(self, 'csv_header', expand=True)

	def render_init(self, scene, depsgraph):
		global ti_start
		ti_start = datetime.now()
		self.rendering = True
		print(f"Index {self.i} | Frame {self.render_queue[0]}")

	def render_complete(self, scene, depsgraph):
		filename = self.filename
		directory = self.directory

		oredername = filename + "_" + "%04d" % self.i + get_format(scene.render.image_settings)
		oreder_path = os.path.join(directory, oredername)

		self.current_frame_list.append(self.render_queue[0])
		
		scene.render.filepath = os.path.join(directory, filename)

		self.report({'INFO'}, str(self.render_queue[0]) + " Frame Render Finished! | File:" + str(oreder_path))

		scene.render_progress = self.i/range_total

		global ti_complete
		ti_complete = datetime.now()
		render_avg_time.append(ti_complete - ti_start)

		if self.background:
			if len(render_avg_time) > 0:
				render_avg_time_seconds = [td.total_seconds() for td in render_avg_time]
				average = sum(render_avg_time_seconds) / len(render_avg_time_seconds)
				print(f'Avg time: {str(timedelta(seconds=average))[:-4]}')
				print(f'Remaining time: {str(timedelta(seconds=average*range_total*(1 - scene.render_progress)))[:-4]}')

		self.i = self.i + 1
		self.render_queue.pop(0)
		self.rendering = False

	def render_cancel(self, scene, depsgraph):
		global ti_complete
		ti_complete = datetime.now()
		render_avg_time.append(ti_complete - ti_start)
		self.current_frame_list.append(self.render_queue[0])
		scene.cancel_key_render = True
		print("RENDER CANCEL")

	def execute(self, context):
		output_path = context.scene.render.filepath
		self.output_path = output_path
		self.directory, self.filename = os.path.split(output_path)
		self.original_frame = context.scene.frame_current
		
		context.scene.cancel_key_render = False
		self.rendering = False
		self.render_queue = []
		self.full_queue = []
		self.current_frame_list = []
		self.i = 0

		self.render_queue = get_keyed(self, context)
		self.full_queue = get_keyed(self, context)

# ----------------------------------------------------------------------------

		# Register callback functionss
		bpy.app.handlers.render_init.clear()
		bpy.app.handlers.render_init.append(self.render_init)

		bpy.app.handlers.render_complete.clear()
		bpy.app.handlers.render_complete.append(self.render_complete)

		bpy.app.handlers.render_cancel.clear()
		bpy.app.handlers.render_cancel.append(self.render_cancel)

		# Lock interface
		bpy.types.RenderSettings.use_lock_interface = True
		
		# Create timer event that runs every second to check if render render_queue needs to be updated
		self.timer_event = context.window_manager.event_timer_add(0.1, window=context.window)
		
		# register this as running in background
		context.window_manager.modal_handler_add(self)

		context.scene.render_progress = 0

		bpy.types.TOPBAR_MT_editor_menus.append(draw_render_progress)
		bpy.types.IHUSEFUL_MT_editor_menus.append(draw_render_progress)

		global range_total
		range_total = len(self.full_queue)

		if self.use_range:
			self.i = len([num for num in self.render_queue if num < self.range_start])
			self.render_queue = [num for num in self.render_queue if num >= self.range_start]
			range_total = len([num for num in self.render_queue if num <= self.range_end])
			
		global render_type
		render_type = 'Keyed'

		global render_avg_time
		render_avg_time = []

		print("Total: " + str(range_total))
		print('Start Keyed Render!')

		return {"RUNNING_MODAL"}
	
	def modal(self, context, event):
		# ESC
		if event.type == 'ESC':
			bpy.types.RenderSettings.use_lock_interface = False
			bpy.types.TOPBAR_MT_editor_menus.remove(draw_render_progress)
			bpy.types.IHUSEFUL_MT_editor_menus.remove(draw_render_progress)
			context.scene.render.filepath = self.output_path

			reorder_render_name(self, context)
			
			if self.export_csv:
				export_csv(self, context)
			
			self.report({'INFO'}, "Render Cancelled!")

			return {'CANCELLED'}
		
		elif event.type == 'TIMER':
			# If cancelled or no items in queue to render, finish.
			if len(self.render_queue) == 0 or context.scene.cancel_key_render is True or (self.use_range and self.render_queue[0] > self.range_end):

				# remove all render callbacks
				bpy.app.handlers.render_init.clear()
				bpy.app.handlers.render_complete.clear()
				bpy.app.handlers.render_cancel.clear()
				
				# remove timer
				context.window_manager.event_timer_remove(self.timer_event)

				bpy.types.TOPBAR_MT_editor_menus.remove(draw_render_progress)
				bpy.types.IHUSEFUL_MT_editor_menus.remove(draw_render_progress)
				
				bpy.types.RenderSettings.use_lock_interface = True

				context.scene.render.filepath = self.output_path
				
				reorder_render_name(self, context)

				if self.export_csv:
					export_csv(self, context)

				self.report({'INFO'}, "Render Finish!")

				if self.kill == True:
					# Define the command to shut down Blender
					command = 'taskkill /f /im blender.exe'
					# Execute the command to shut down Blender
					subprocess.Popen(command, shell=True)

				return {"FINISHED"}

			# nothing is rendering and there are items in queue
			elif self.rendering is False:
				filename = self.filename
				directory = self.directory

				if context.scene.use_nodes == True and any(node.type == 'OUTPUT_FILE' for node in context.scene.node_tree.nodes):
					write = False
				else:
					write = True

				context.scene.frame_current = self.render_queue[0]
				rendername = filename + "%04d" % self.render_queue[0]
				render_path = os.path.join(directory, rendername)
				context.scene.render.filepath = render_path
				bpy.ops.render.render("INVOKE_DEFAULT", write_still=write)

				return {"PASS_THROUGH"}
				
		return {"PASS_THROUGH"}

class RENDER_OT_Shots(bpy.types.Operator):
	bl_idname = "render.shots"
	bl_label = "Anime Shots Render"
	bl_options = {'REGISTER', 'UNDO'}

	rendering = None
	timer_event = None
	i = 0
	directory = None
	filename = None
	original_camera = None
	output_path = None
	camera_list = None

	def render_init(self, scene, depsgraph):
		global ti_start
		ti_start = datetime.now()
		self.rendering = True
		print(f"Shot | {self.camera_list[self.i]}")

	def render_complete(self, scene, depsgraph):
		filename = self.filename
		directory = self.directory

		shots = self.camera_list

		rendername = filename + '_' + shots[self.i]
		render_path = os.path.join(directory, rendername)

		scene.render.filepath = render_path

		self.report({'INFO'}, f"Shots {str(self.camera_list[self.i])} Render Finished! | File:" + str(render_path))

		scene.render_progress = self.i/len(self.camera_list)

		global render_type
		render_type = 'Shots'

		global ti_complete
		ti_complete = datetime.now()
		render_avg_time.append(ti_complete - ti_start)

		self.i = self.i + 1
		self.rendering = False

	def render_cancel(self, scene, depsgraph):
		global ti_complete
		ti_complete = datetime.now()
		render_avg_time.append(ti_complete - ti_start)
		scene.cancel_key_render = True
		print("RENDER CANCEL")

	def execute(self, context):
		output_path = context.scene.render.filepath
		self.output_path = output_path
		self.directory, self.filename = os.path.split(output_path)
		self.original_camera = context.scene.camera
		context.scene.cancel_key_render = False
		self.rendering = False
		self.camera_list = []
		self.i = 0
		self.camera_list = list(filter(None,[obj.name if obj.type == 'CAMERA' and obj.hide_render == False and context.scene.name == obj.users_scene[0].name else None for obj in bpy.data.objects])) 

# ----------------------------------------------------------------------------

		# Register callback functionss
		bpy.app.handlers.render_init.clear()
		bpy.app.handlers.render_init.append(self.render_init)

		bpy.app.handlers.render_complete.clear()
		bpy.app.handlers.render_complete.append(self.render_complete)

		bpy.app.handlers.render_cancel.clear()
		bpy.app.handlers.render_cancel.append(self.render_cancel)

		# Lock interface
		bpy.types.RenderSettings.use_lock_interface = True
		
		# Create timer event that runs every second to check if render render_queue needs to be updated
		self.timer_event = context.window_manager.event_timer_add(0.1, window=context.window)
		
		# register this as running in background
		context.window_manager.modal_handler_add(self)

		context.scene.render_progress = 0

		bpy.types.TOPBAR_MT_editor_menus.append(draw_render_progress)
		bpy.types.IHUSEFUL_MT_editor_menus.append(draw_render_progress)

		global range_total
		range_total = len(self.camera_list)

		global render_avg_time
		render_avg_time = []

		print("Total: " + str(range_total))
		print('Start Keyed Render!')

		return {"RUNNING_MODAL"}
	
	def modal(self, context, event):
		
		if context.scene.use_nodes == True and any(node.type == 'OUTPUT_FILE' for node in context.scene.node_tree.nodes):
			write = False
		else:
			write = True

		# ESC
		if event.type == 'ESC':
			bpy.types.RenderSettings.use_lock_interface = False
			
			bpy.types.TOPBAR_MT_editor_menus.remove(draw_render_progress)
			bpy.types.IHUSEFUL_MT_editor_menus.remove(draw_render_progress)
			context.scene.render.filepath = self.output_path
			context.scene.camera = self.original_camera

			self.report({'INFO'}, "Render Cancelled!")

			return {'CANCELLED'}
		
		elif event.type == 'TIMER':
			# If cancelled or no items in queue to render, finish.
			if self.i == len(self.camera_list) or context.scene.cancel_key_render is True:

				# remove all render callbacks
				bpy.app.handlers.render_init.clear()
				bpy.app.handlers.render_complete.clear()
				bpy.app.handlers.render_cancel.clear()
				
				# remove timer
				context.window_manager.event_timer_remove(self.timer_event)

				bpy.types.TOPBAR_MT_editor_menus.remove(draw_render_progress)
				bpy.types.IHUSEFUL_MT_editor_menus.remove(draw_render_progress)
				
				bpy.types.RenderSettings.use_lock_interface = True

				context.scene.render.filepath = self.output_path
				context.scene.camera = self.original_camera
				self.report({'INFO'}, "Render Finish!")
				
				return {"FINISHED"}

			# nothing is rendering and there are items in queue
			elif self.rendering is False:
				filename = self.filename
				directory = self.directory
				shots = self.camera_list
				context.scene.camera = bpy.data.objects[shots[self.i]]
				rendername = filename + '_' + shots[self.i]
				render_path = os.path.join(directory, rendername)
				context.scene.render.filepath = render_path
				
				bpy.ops.render.render("INVOKE_DEFAULT", write_still=write)

				return {"PASS_THROUGH"}
				
		return {"PASS_THROUGH"}

def draw_keyed_render(self, context):
	self.layout.separator()
	self.layout.operator("render.keyed", text = "Render Keyed Anime", icon = 'KEYFRAME_HLT')
	self.layout.operator("render.shots", text = "Render Shots", icon = 'VIEW_CAMERA')
	
classes = (
			RENDER_OT_Keyed,
			RENDER_OT_Shots,
		  )

def register(): 
	from bpy.utils import register_class
	for cls in classes:
		register_class(cls)

	bpy.types.Scene.cancel_key_render = bpy.props.BoolProperty(
			name="",
			default = False,
		)

	bpy.types.Scene.render_progress = bpy.props.FloatProperty(
			name="",
			default = 0,
			min=0,
			max=1
		)
	
	bpy.types.TOPBAR_MT_render.append(draw_keyed_render)

def unregister():
	from bpy.utils import unregister_class
	for cls in reversed(classes):
		unregister_class(cls)

	bpy.types.TOPBAR_MT_render.remove(draw_keyed_render)

	del bpy.types.Scene.render_progress
	del bpy.types.Scene.cancel_key_render
