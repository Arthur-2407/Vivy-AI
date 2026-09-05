import os
import glob
for root, dirs, files in os.walk('D:\\Vivy\\hub'):
    for file in files:
        if 'session' in file:
            print(os.path.join(root, file))
