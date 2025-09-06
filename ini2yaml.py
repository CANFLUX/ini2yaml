import re
import os
import sys
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import PlainScalarString, SingleQuotedScalarString, LiteralScalarString
from ruamel.yaml.scalarint import ScalarInt
from ruamel.yaml.scalarfloat import ScalarFloat
from ruamel.yaml.scalarbool import ScalarBoolean
from datetime import datetime,timedelta
from dateutil.parser import parse as dateparse
from dataclasses import dataclass,field, MISSING, _MISSING_TYPE
from helperFunctions import asdict_repr,packDict

yaml = YAML()

def safeString(obj,delim=','):
    def check_reserved_words(s):
        # Some words are parsed to bool in different yaml interpreters
        # If code is expecting 'on' and gets a bool, will cause issues.
        # Use sparingly, only for words needed.  By default, these words will be converted 
        # y|Y|yes|Yes|YES|n|N|no|No|NO|
        # true|True|TRUE|false|False|FALSE|
        # on|On|ON|off|Off|OFF
        if type(s) is str and s.lower() in ['on','off']:
            s = SingleQuotedScalarString(s)
        return(s)
    if type(obj) is set:
        return(','.join(list(check_reserved_words(obj))))
    elif type(obj) is dict and not len(obj):
        return(None)

    else:
        return(check_reserved_words(obj))

@dataclass(kw_only=True)
class configuration:
    metadata: dict = field(default_factory=dict)
    globalVars: dict = field(default_factory=dict)
    Trace: dict = field(default_factory=dict)
    Include: dict = field(default_factory=dict)

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
    variableName: str = field(default='', metadata={'stage': 'common'})
    title: str = field(default='', metadata={'stage': 'common'})
    originalVariable: str = field(default='', metadata={'stage': 'firststage'})
    inputFileName: set = field(default_factory=str, metadata={'stage': 'firststage'})
    inputFileName_dates: list = field(default_factory=list, metadata={'stage': 'firststage'})
    measurementType: str = field(default='', metadata={'stage': 'firststage'})
    units: str = field(default='', metadata={'stage': 'common'})
    instrument: str = field(default='', metadata={'stage': 'firststage'})
    instrumentType: str = field(default='', metadata={'stage': 'firststage'})
    instrumentSN: str = field(default='', metadata={'stage': 'firststage'})
    loggedCalibration: list = field(default_factory=list, metadata={'stage': 'firststage'})
    currentCalibration: list = field(default_factory=list, metadata={'stage': 'firststage'})
    minMax: list = field(default_factory=list, metadata={'stage': 'firststage'})
    clamped_minMax: list = field(default_factory=list, metadata={'stage': 'firststage'})
    zeroPt: list = field(default_factory=list, metadata={'stage': 'firststage'})
    comments: str = field(default='', metadata={'stage': 'firststage'})
    dependent: str = field(default='', metadata={'stage': 'firststage'})
    Evaluate: str = field(default='', metadata={'stage': 'secondstage'})

    def parse_from_ini_string(self,ini_string,stage='firststage',fields_on_the_fly=False,verbose=False):
        # A bit hack-key, remove appended fields from previous instance
        # adding fields on the fly ensure the non-standard keys are transferred to the new yaml files
        if fields_on_the_fly:
            flds = list(self.__dataclass_fields__.keys())
            for k in flds:
                if k not in self.__dict__.keys():
                    self.__dataclass_fields__.pop(k)
        # reset repr in case it was turned off in previous instance
        for k in self.__dataclass_fields__:
            self.__dataclass_fields__[k].repr=True
        # parse the trace from an ini file
        # Define python versions of matlab keywords
        lb_key = '~linebreak~'
        Inf = float('inf')
        NaN = float('NaN')
        new_string = ''
        pattern = r"'(.*?)'"
        def lb_replacer(match):
            return(match[0].replace('\n',lb_key))
        new_string = re.sub(pattern,lb_replacer,ini_string, flags=re.DOTALL)
        key_val_pairs = {l.split('=',1)[0].strip():l.split('=',1)[-1].strip() 
                        for l in new_string.split('\n') 
                        if '=' in l and
                        not l.strip().startswith('%') and
                        not l.strip().startswith(';')}
        for k,v in key_val_pairs.items():
            v = v.replace(lb_key,'\n')
            if k == 'Evaluate':
                # don't evaluate these strings, re-add datenum calls for Evaluate compatibility
                pattern = r'datetime\((.*?)\)'
                def add_datenum(m):
                    if ',' not in m.group(1):
                        try:
                            test = datetime(m.group(1))
                            return(f"datenum({m.group(0)})")
                        except:
                            pass
                    return(m.group(0))
                v = re.sub(pattern,add_datenum,v)
                v = v.split("'")[1]
                v = '\n'.join([u.split('%')[0] for u in v.split('\n')])
                v = re.sub("[ \t]",'',v)
                self.__dict__[k] = LiteralScalarString(v.strip())
            else:
                v = CleanedText(text=v).text
                if k == 'units':
                    v = v.strip().encode('unicode_escape').decode()
                try:
                    v = v.replace('\n',' ')
                    self.__dict__[k] = eval(v.strip()) 
                    if k not in self.__dataclass_fields__ and not fields_on_the_fly and verbose:
                        print(f"Field {k} is not a default field, run with fields_on_the_fly=True to allow for dynamic field generation, or edit the source code ...")
                    elif not type(self.__dict__[k])==self.__dataclass_fields__[k].type:
                        try:
                            if self.__dataclass_fields__[k].type in [str,float,int] and len(self.__dict__[k]) == 0:
                                self.__dict__[k] = self.__dataclass_fields__[k].default
                            elif len(self.__dict__[k]) == 0:
                                self.__dict__[k] = self.__dataclass_fields__[k].default_factory()
                            else:
                                a = 1/0
                        except:
                            print('\n\n\n!!! Warning !!!')
                            print(f'Check type for {self.__dict__["variableName"]}:{k}')
                            print('!!!\n\n\n')
                except:
                    print(f'Error in key "{k}" could not parse {v}, see traceblock for possible errors:')
                    print(ini_string)
            # convert any matlab cells (read in python as sets) to comma delimited string
            self.__dict__[k] = safeString(self.__dict__[k])
        if fields_on_the_fly:
            for k in self.__dict__:
                if k not in self.__dataclass_fields__:
                    self.__dataclass_fields__[k] = field(metadata={'stage':'non-standard'})
        for k,v in self.__dataclass_fields__.items():
            if v.metadata['stage'] != stage and v.metadata['stage'] != 'common':
                if self.__dict__[k] == v.default:
                    self.__dataclass_fields__[k].repr=False
                elif v.default_factory is not MISSING and self.__dict__[k] == v.default_factory():
                    self.__dataclass_fields__[k].repr=False

@dataclass(kw_only=True)
class parser:
    root: str
    SiteID: str = None
    stage: str = None
    include: str = None
    verbose: bool = True
    base_prop_by_stage: dict = field(default_factory=lambda:{
        'firststage':['SiteID','Site_name','Difference_GMT_to_local_time','Timezone'],
        'secondstage':['SiteID','Site_name','input_path','output_path','high_level_path','searchPath']
    })
    fields_on_the_fly = False # If true, will allow non-standard fields which are not declared explicitly in Trace class

    def __post_init__(self):
        self.config = configuration()
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
            
        self.parse_traces()
        self.parse_globals()
        self.parse_includes()


        if not self.include:
            self.config.Include = list(self.config.Include.keys())
            
            # for prop in self.base_prop_by_stage[self.stage]:
            #     res = re.findall(prop+r'\s*=\s*(.*)\n',self.text)
            #     if len(res):
            #         self.config.__dict__[prop] = eval(res[0].strip())
            #         self.text = re.sub(prop+r'\s*=\s*(.*)\n','',self.text)
        outpath = os.path.join(self.root,fname.replace('.ini','.yml'))
        self.write(outpath)
        # else:
        #     # Delete empty fields from includes
        #     for c in self.config.__dataclass_fields__.keys():
        #         if (self.config.__dict__[c] == self.config.__dataclass_fields__[c].default or 
        #             self.config.__dict__[c] == self.config.__dataclass_fields__[c].default_factory()):
        #             del self.config.__dict__[c]
        #     outpath = os.path.join(self.root,fname.replace('.ini','.yml'))
        #     self.write(outpath)

    def parse_includes(self):
        # Call self recursively to parse each include file
        if '#include' in self.ini_string:
            includes = [line for line in self.ini_string.splitlines() if line.startswith('#include')]
            for include in includes:
                fname = include.split('#include')[-1].strip()
                self.config.Include[fname.split('.')[0]] = parser(root=self.root,include=fname,stage=self.stage,verbose=self.verbose).config.Trace
                # Remove lines which have been processed
                self.ini_string = self.ini_string.replace(include,' ')
                
    def parse_traces(self):
        # Find trace blocks
        pattern = r"\[Trace\](.*?)\[End\]"
        matches = re.findall(pattern, self.ini_string, flags=re.DOTALL)
        self.trace_blocks = []
        for match in matches:
            trace = Trace()
            trace.parse_from_ini_string(match,stage=self.stage,fields_on_the_fly=self.fields_on_the_fly,verbose=self.verbose)
            if trace.variableName != '':
                self.config.Trace[trace.variableName] = asdict_repr.asdict_repr(trace)
            self.ini_string = self.ini_string.replace(f'[Trace]{match}[End]','')
        self.ini_string = self.ini_string.strip()

        
    def parse_globals(self):
        
        base_vars = [l for l in self.ini_string.split('\n') 
                    if '=' in l and len(l.strip()) and
                    not l.strip().startswith('%') and
                    not l.strip().startswith(';') and
                    'globalVars' not in l]
        for b in base_vars:
            k,v = b.split('=',1)
            k,v = k.strip(),CleanedText(text=v).text
            exec(f'{k}={v}')
            if k in self.base_prop_by_stage[self.stage]:
                self.config.metadata[k] = safeString(eval(v))
                print(self.config.metadata[k])
            self.ini_string = self.ini_string.replace(b,'')
        # extract globalVars
        globalVars = [l for l in self.ini_string.split('\n') if l.startswith('globalVars')]
        for g in globalVars:
            self.ini_string = self.ini_string.replace(g,'')
        globalVars = '\n'.join(globalVars)
        if not len(globalVars):
            return
        for i in range(3,0,-1):
            # Append ~! to end of each pattern to prevent partial matches
            pat = r"globalVars\.(\w+)".replace(r'\.(\w+)',r'\.(\w+)'*i)
            sub = r"globalVariables."+r'.'.join([fr"\{i+1}" for i in range(i)])+r'~!'
            globalVars = re.sub(pat,sub,globalVars)
        globalVars = globalVars.replace('globalVariables','globalVars').replace('~!','')
        # Convert to dict
        globalVars = [l.split('=',1) for l in globalVars.split('\n')]
        globalVars = {l[0].strip():l[-1].strip() for l in globalVars if l[0].strip() != ''}
        # Try to evaluate what can be evaluated
        # Identify recursive values to be set as anchors eval it fails
        for key,value in globalVars.items():
            if key != 'Evaluate':
                value = CleanedText(text=value).text
            try:
                globalVars[key] = safeString(eval(value))
            except:
                print(value)
                print(value.strip())
                if 'globalVars' not in value:
                    print(key,value)
                    breakpoint()
                    sys.exit(f"Line {sys._getframe().f_lineno} failed to parse non-recurvsive global var")
                elif value.startswith('['):
                    vlist = [v.strip() for v in value.strip('[]').split(',')]
                    globalVars[key] = []
                else:
                    globalVars[key] = None
                    vlist = [value]
                for i,v in enumerate(vlist):
                    if v in globalVars.keys():
                        # define ruamel.yaml anchors for assorted variable types
                        # for recursive referencing
                        if type(globalVars[v]) is list:
                            globalVars[v] = CommentedSeq(globalVars[v])
                            globalVars[v].yaml_set_anchor(v.replace('.','_'),always_dump=True)
                        elif type(globalVars[v]) is dict:
                            globalVars[v] = CommentedMap(globalVars[v])
                            globalVars[v].yaml_set_anchor(v.replace('.','_'),always_dump=True)
                        elif type(globalVars[v]) is str:
                            globalVars[v] = PlainScalarString(globalVars[v])
                            globalVars[v].yaml_set_anchor(v.replace('.','_'),always_dump=True)
                        elif type(globalVars[v]) is int:
                            globalVars[v] = ScalarInt(globalVars[v])
                            globalVars[v].yaml_set_anchor(v.replace('.','_'),always_dump=True)
                        elif type(globalVars[v]) is float:
                            globalVars[v] = ScalarFloat(globalVars[v])
                            globalVars[v].yaml_set_anchor(v.replace('.','_'),always_dump=True)
                        elif type(globalVars[v]) is bool:
                            globalVars[v] = ScalarBoolean(globalVars[v])
                            globalVars[v].yaml_set_anchor(v.replace('.','_'),always_dump=True)
                            
                    # Assign anchors to recursive references
                    if type(globalVars[key]) is list:
                        if v in globalVars.keys():
                            globalVars[key].append(globalVars[v])
                        else:
                            globalVars[key].append(eval(v))
                    else:
                        globalVars[key] = globalVars[v]
        # custom function for converting delimited strings to nested dict
        globalVars = packDict.packDict(globalVars,format='.')
        def sub_anchors(dct={},anc={}):
            # Preserve ruamel anchors
            if type(dct) is dict:
                for key,value in dct.items():
                    if type(value) is dict:
                        dct[key],anc = sub_anchors(value,anc)
                    elif hasattr(value,'anchor'):
                        if str(value.anchor) not in anc.keys():
                            anc[str(value.anchor)] = value
                            dct[key] = value
                        else:
                            dct[key] = anc[str(value.anchor)]
                    elif type(value) is list:
                        dct[key],anc = sub_anchors(value,anc)
            elif type(dct) is list:
                for i,value in enumerate(dct):
                    if type(value) is list:
                        dct[i],anc = sub_anchors(value,anc)
                    elif hasattr(value,'anchor'):
                        if str(value.anchor) not in anc.keys():
                            anc[str(value.anchor)] = value
                            dct[i] = value
                        else:
                            dct[i] = anc[str(value.anchor)]
            return(dct,anc)
        globalVars,_ = sub_anchors(globalVars)
        self.config.globalVars = globalVars['globalVars']

        
    def write(self,outpath):
        print('Writing ',outpath)
        with open(outpath,'w+',encoding="utf-8") as f:
            yaml.dump(self.config.__dict__,f)
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

@dataclass(kw_only=True)
class CleanedText:
    text: str
    bp: bool = False
    
    def __post_init__(self):
        self.clean_text()

    def clean_text(self):
        if self.bp: breakpoint()
        # Exclude comments, but preserve percent signs within strings
        pattern = r"(\"[^\"]*\"|'[^']*')|%(.*)"
        def replacer(match):
            if match.group(1):  # quoted string
                return match.group(1)
            else:               # bare %
                return ''
        self.text = re.sub(pattern, replacer, self.text)
        # Delete blank lines
        self.text = '\n'.join([l.strip() for l in self.text.split('\n') if len(l.strip()) and not l.strip().startswith(';')])
        # Replace functions names which are directly translatable to python
        self.text = self.replace_num2str(text=self.text)
        # Convert to standard pythonic dates
        self.text = self.replace_datenum(text=self.text) 
        # Add commas to space delimited lists 
        self.text = self.format_lists(text=self.text)    
        # Ensure all equal signs have space on each side
        self.text = self.text.replace('=',' = ')
        # Add spaces before/after brackets to make parsing simpler
        self.text = self.text.replace('[',' [ ').replace(']',' ] ')
        # Except for start/end blocks
        self.text = self.text.replace(' [ End ] ','[End]').replace(' [ Trace ] ','[Trace]')
        self.text = self.text.strip()
    

    def replace_num2str(self,text):
        # Exclude comments, but preserve percent signs within strings
        pattern = r'\s*num2str\((.*?)\)\s*'
        def replacer(match):
            inner = match.group(1) 
            return (f" {inner} ")
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
                inner = ','.join(str(int(i)) for i in inner.split(','))
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
            inner = re.sub(r"'\s*&\s*'*","'&'",inner.strip())
            inner = re.sub(r'(?<=[^,;])\s+(?=[^,])',' , ',inner).replace("'&'","' & '")
            if inner.count(';'):
                inner = [inn for inn in inner.split(';') if len(inn.strip())>0]
                if len(inner)==1:
                    inner = inner[0]
                else:
                    inner ='['+('],['.join(inner))+']'
            return (f'[{inner}]')
        fmtd = re.sub(pattern,replace_spaces_and_semicolons,text)
        # Get rid of quoted lists if they exist
        def replace_quotes(m):
            return(f'[{m.group(1)}]')
        pattern = r"'\[(.*?)\]'"
        fmtd = re.sub(pattern,replace_quotes,fmtd)
        pattern = r"'\[(.*?)\];'"
        fmtd = re.sub(pattern,replace_quotes,fmtd)
        # convert {[..]} to [..]
        pattern = r"{\[(.*?)\]}"
        def clip_brackets(m):
            return('['+m.group(1)+']')
        fmtd = re.sub(pattern,clip_brackets,fmtd)
        return(fmtd)
