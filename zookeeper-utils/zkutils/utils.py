import os
import logging
import subprocess


log = logging.getLogger(__name__)


class CommandError(Exception):
   def __init__(self, stdout, stderr):
      self.stdout = stdout
      self.stderr = stderr
      super(CommandError, self)\
         .__init__("stdout: {stdout}\nstderr: {stderr}" \
         .format(stdout=stdout,stderr=stderr))


def run_command(command):
   log.debug(command)
   result = subprocess.Popen(
               command,
               shell=True,
               stdout=subprocess.PIPE,
               stderr=subprocess.PIPE
            )
   stdout, stderr = result.communicate()
   stdout = stdout.strip()
   stderr = stderr.strip()
   if stderr:
      log.error(stderr)
      log.error(stdout)
      raise CommandError(stdout, stderr)
   return stdout


def save_to_file(filename, content):
   ''' Performs backup of existing file and saves the new
   content to the file.
   '''
   content = str(content)

   # Backup old content
   if os.path.isfile(filename):
      backup_filename = '{filename}.bk'.format(filename=filename)
      with open(backup_filename, 'w') as fwrite:
         with open(filename, 'r') as fread:
            old_content = fread.read()
         fwrite.write(old_content)
      log.info('Backed up filename=%s' % backup_filename)

   # Save new content
   with open(filename, 'w') as fwrite:
      fwrite.write(content)
   log.info('Saved filename=%s' % filename)
