from . import(
    keyed_render,
)

module_list = (
    keyed_render,
)

def register():
    for mod in module_list:
        mod.register()

def unregister():
    for mod in reversed(module_list):
        mod.unregister()

if __name__ == "__main__":
    register()