import re
import os
import sys
import yaml
from datetime import datetime,timedelta
from dateutil.parser import parse as dateparse
from dataclasses import dataclass,field
from helperFunctions import updateDict,asdict_repr

def set2string(obj,delim=','):
    if type(obj) is set:
        return(','.join(list(obj)))
    else:
        return(obj)
    

@dataclass(kw_only=True)
class configuration:
    Site_name: str = None
    SiteID: str = None
    Difference_GMT_to_local_time: int = None
    Timezone: int = None
    globalVars: dict = field(default_factory=dict)
    Trace: dict = field(default_factory=dict)
    Include: dict = field(default_factory=dict)
    # Comments: list = field(default_factory=lambda:[])

@dataclass(kw_only=True)
class yamlConfig:
    verbose: bool = True
    config_path: str = None
    config_dict: dict = None

    def __post_init__(self):
        if self.config_path and os.path.isfile(self.config_path):
            if self.verbose:
                print(self.config_path)
            with open(self.config_path) as f:
                self.config_dict = yaml.safe_load(f)

@dataclass(kw_only=True)
class iniFile:
    verbose: bool = True
    ini_path: str = None
    ini_string: str = None

    def __post_init__(self):
        if os.path.isfile(self.ini_path):
            if self.verbose:
                print(self.ini_path)
            with open(self.ini_path) as f:
                self.ini_string = f.read()

@dataclass(kw_only=True)
class Trace:
    # The expected fields and their corresponding types for a trace object
    variableName: str = None
    title: str = None
    originalVariable: str = None
    inputFileName: str = field(default_factory=lambda:{})
    inputFileName_dates: list = field(default_factory=lambda:[])
    measurementType: str = None
    units: str = None
    instrument: str = None
    instrumentType: str = None
    instrumentSN: str = None
    calibrationDates: list = field(default_factory=lambda:[],repr=False) # depreciated settings to be parsed but not written
    loggedCalibration: list = field(default_factory=lambda:[])
    currentCalibration: list = field(default_factory=lambda:[])
    minMax: list = field(default_factory=lambda:[])
    clamped_minMax: list = field(default_factory=lambda:[])
    zeroPt: list = field(default_factory=lambda:[])
    comments: str = None
    dependent: str = None
    Evaluate: str = None

    def parse_from_ini_string(self,ini_string):
        # parse the trace from an ini file
        # Define python versions of matlab keywords
        Inf = float('inf')
        NaN = float('NaN')
        keys = self.__dataclass_fields__.keys()
        patterns = [key + r'\s*=' for key in keys]
        for pattern,key in zip(patterns,keys):
            ini_string = re.sub(pattern,f'~key~{key}~value~',ini_string.strip())
        split_string = re.split('~key~|~value~',ini_string)
        split_string = [t for t in split_string if t.strip()!='']
        out = {k:v for k,v in zip(split_string[::2],split_string[1::2])}
        for k,v in out.items():
            if k == 'Evaluate':
                # don't evaluate these strings
                self.__dict__[k] = v.strip().strip("'")
            else:
                if k == 'units':
                    v = v.strip().encode('unicode_escape').decode()
                self.__dict__[k] = eval(v.strip())    
            # convert any matlab cells (read in python as sets) to comma delimited string
            self.__dict__[k] = set2string(self.__dict__[k])

    def dump_to_ini_string(self,config):
        pass

@dataclass
class parser:
    root: str
    SiteID: str = None
    stage: str = None
    include: str = None
    verbose: bool = True

    def __post_init__(self):
        self.config = configuration(SiteID=self.SiteID)
        if self.SiteID is not None:
            fname = os.path.join(self.root,self.SiteID,f'{self.SiteID}_{self.stage}.ini')
        else:
            fname = os.path.join(self.root,self.include)
        if os.path.isfile(fname):
            with open(fname,encoding='utf-8') as f:
                if self.verbose:
                    print('reading ',fname)
                self.ini_string = f.read()
        else:
            sys.exit('Not a file: '+fname)
        self.clean_text()
        # First read any embedded include files
        self.parse_globals()
        self.parse_traces()
        self.parse_includes()
        if not self.include:
            self.config.Include = list(self.config.Include.keys())
            
            for prop in ['SiteID','Site_name','Difference_GMT_to_local_time','Timezone']:
                res = re.findall(prop+r'\s*=\s*(.*)\n',self.text)
                if len(res):
                    self.config.__dict__[prop] = eval(res[0].strip())
                    self.text = re.sub(prop+r'\s*=\s*(.*)\n','',self.text)
            outpath = os.path.join(self.root,fname.replace('.ini','.yml'))
            self.write(outpath)
        else:
            # Delete empty fields from includes
            for c in self.config.__dataclass_fields__.keys():
                if (self.config.__dict__[c] == self.config.__dataclass_fields__[c].default or 
                    self.config.__dict__[c] == self.config.__dataclass_fields__[c].default_factory()):
                    del self.config.__dict__[c]
            outpath = os.path.join(self.root,fname.replace('.ini','.yml'))
            self.write(outpath)

    def clean_text(self):
        # Exclude comments, but preserve percent signs within strings
        pattern = r"(\"[^\"]*\"|'[^']*')|%(.*)\n"
        def replacer(match):
            if match.group(1):  # quoted string
                return match.group(1)
            else:               # bare %
                return '\n'
        self.text = re.sub(pattern, replacer, self.ini_string)
        # Delete blank lines
        self.text = '\n'.join([l.strip() for l in self.text.split('\n') if len(l.strip())])
        # Replace functions names which are directly translatable to python
        self.text = self.replace_num2str(text=self.text)
        # Convert to standard pythonic dates
        self.text = self.replace_datenum(text=self.text) 
        # Add commas to space delimited lists 
        self.text = self.format_lists(text=self.text)      

    def replace_num2str(self,text):
        # Exclude comments, but preserve percent signs within strings
        pattern = r'\s*num2str\((.*?)\)\s*'
        def replacer(match):
            inner = match.group(1) 
            return (f"+str({inner})+")
        return(re.sub(pattern, replacer, text))


    def replace_datenum(self,text):
        # Replace all depreciated datenum objects with datetime object which is valid in both python and matlab
        # write a wrapper to go from datetime to depreciated datenum in matlab
        pattern = r'datenum\((.*?)\)'  # capture inside quotes
        def get_date(m):
            inner = m.group(1)
            if inner.startswith('"') or inner.startswith("'"):
                inner = inner.strip('"').strip("'")
                if '24:00' in inner:
                    inner = inner.replace('24:00','23:59')
                    d = dateparse(inner)+timedelta(minutes=1)
                else:
                    d = dateparse(inner)
            else:
                d = eval('datetime('+inner+')')
            # format datestring, ~_~ is a stand in for a space to be replaced after list formatting
            d = d.strftime("%Y-%m-%dT%H:%M:%S")
            return(f'"{d}"')
        return(re.sub(pattern,get_date,text))
        
    def format_lists(self,text):
        # need to format correctly for parsing to python
        # matlab allows list to be delimited by spaces, python requires commas
        # matlab dimensions are denoted by semicolons, python uses nested brackets
        pattern = r"\[(.*?)\]"
        def replace_spaces_and_semicolons(m):
            inner = m.group(1)
            inner = re.sub(r"\s*'\s*&\s*'\s*","'&'",inner.strip())
            inner = re.sub(r'(?<=[^,])\s+(?=[^,])',',',inner).replace("'&'","+' & '+").replace(';,',';')
            if inner.count(';'):
                inner = [inn for inn in inner.split(';') if len(inn.strip())>0]
                if len(inner)==1:
                    inner = inner[0]
                else:
                    inner ='['+('],['.join(inner))+']'
            return (f'[{inner}]')
        fmtd = re.sub(pattern,replace_spaces_and_semicolons,text)
        pattern = r"'\[(.*?)\]'"
        def replace_quotes(m):
            return(f'[{m.group(1)}]')
        fmtd = re.sub(pattern,replace_quotes,fmtd)
        # convert {[..]} to {}, cells parsed as sets, can't contain lists
        pattern = r"{\[(.*?)\]}"
        def replace_quotes(m):
            return('{'+m.group(1)+'}')
        fmtd = re.sub(pattern,replace_quotes,fmtd)
        return(fmtd)

    def parse_includes(self):
        # Call self recursively to parse each include file
        if '#include' in self.ini_string:
            includes = [line for line in self.text.splitlines() if line.startswith('#include')]
            for include in includes:
                fname = include.split('#include')[-1].strip()
                self.config.Include[fname.split('.')[0]] = parser(root=self.root,include=fname,verbose=self.verbose).config.Trace
                # Remove lines which have been processed
                self.text = self.text.replace(include,' ')
    
    def parse_traces(self):
        # Find trace blocks
        pattern = r"\[Trace\](.*?)\[End\]"
        matches = re.findall(pattern, self.text, flags=re.DOTALL)
        self.trace_blocks = []
        for match in matches:
            trace = Trace()
            trace.parse_from_ini_string(match)
            self.config.Trace[trace.variableName] = asdict_repr.asdict_repr(trace)
            self.text = self.text.replace(f'[Trace]{match}[End]','')
        self.text = self.text.strip()

    def parse_globals(self):
        self.temp = {}
        p_sub = {
            # Replace globals at start of line (assumes max depth of 3)
            r"globalVars\.(\w+)\s*=":r"temp_globalVars['\i']=",
            # Replace recursive globals to right of equal sign
            # Lists first
            r"globalVars\.(\w+)\s*,":r"self.config.globalVars['\i'],",
            r"globalVars\.(\w+)\s*\]":r"self.config.globalVars['\i']]",
            # Singles next
            r"globalVars\.(\w+)\s*\n":r"self.config.globalVars['\i']\n",
            r"globalVars\.(\w+)\s*":r"self.config.globalVars['\i']"
        }
        for key,value in p_sub.items():
            for i in range(3,0,-1):
                k = key.replace(r'\.(\w+)',r'\.(\w+)'*i)
                v = value.replace(r"['\i']",''.join([r"['\i']".replace('i',str(j+1)) for j in range(i)]))
                pattern = re.compile(k)
                self.text = pattern.sub(v,self.text)        
        def make_temp(text):
            temp_globalVars = {}
            t = ''
            for v in text.split("']"):
                if len(v.strip())>0:
                    t = t+v+"']"
                    exec(t+'={}')
            return(temp_globalVars)
        for line in self.text.split('\n'):
            if line.startswith('temp_globalVars'):
                obj,val = line.split('=',1)
                temp_globalVars = make_temp(obj)
                print(val)
                '&'
                val = set2string(eval(val))
                exec(f"{obj}=val")
                self.config.globalVars = updateDict.updateDict(self.config.globalVars,temp_globalVars)


    def write(self,outpath):
        print('Writing ',outpath)
        with open(outpath,'w+') as f:
            yaml.safe_dump(self.config.__dict__,f,sort_keys=False)
        self.cleanKeys(outpath)
    
    def cleanKeys(self,outpath):
        # Hardcoded custom translations for now
        # Can give more nuanced approach later if it becomes necessary
        patterns = {'Difference_GMT_to_local_time':'Diff_GMT_to_local_time'}
        with open(outpath) as f:
            ymlstring = f.read()
        for k,v in patterns.items():
            ymlstring = ymlstring.replace(k,v)
        with open(outpath,'w+') as f:
            f.write(ymlstring)