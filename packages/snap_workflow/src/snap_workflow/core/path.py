import os,sys
from .strings import *
def get_root(relative_to="."):# {{{
    start = os.getcwd()
    os.chdir(relative_to)
    old_path = ''
    new_path = os.path.realpath('.')
    count = 0
    while new_path != old_path:
        if os.path.isdir(new_path + "/.workflow"):
            ret_path = f".{'/..'*count}"
            os.chdir(start)
            return ret_path
        old_path = new_path
        new_path = os.path.realpath(new_path + "/..")
        count += 1
    os.chdir(start)
    raise Exception("Not in a workflow system. Run workflow init to start setup")

# }}}
class From_Root():# {{{
    def __init__(self):
        return

    def __enter__(self):
        self.start = os.getcwd()
        self.root = get_root()
        os.chdir(self.root)
        return

    def __exit__(self,exc_type,exc_val,traceback):
        os.chdir(self.start)
        return
# }}}
class From_Dir():# {{{
    def __init__(self,from_dir=None):
        self.start = os.getcwd()
        self.from_dir = from_dir
        return

    def __enter__(self):
        os.chdir(self.from_dir)
        return

    def __exit__(self,exc_type,exc_val,traceback):
        os.chdir(self.start)
        return
# }}}
def make_sym(real,link,overwrite=False):# {{{
    if not os.path.islink(link):
        os.symlink(real,link) 
    elif os.path.islink(link) and not os.path.exists(link):
        os.remove(link)
        os.symlink(real,link) 
    elif overwrite:
        os.remove(link)
        os.symlink(real,link) 
    return
# }}}
def clear_directory(job_path):# {{{
    import shutil
    for filename in os.listdir(job_path):
        file_path = os.path.join(job_path,filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))# }}}
