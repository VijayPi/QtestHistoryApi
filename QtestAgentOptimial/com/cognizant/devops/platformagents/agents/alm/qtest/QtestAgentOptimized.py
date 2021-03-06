#-------------------------------------------------------------------------------
# Copyright 2017 Cognizant Technology Solutions
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License.  You may obtain a copy
# of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations under
# the License.
#-------------------------------------------------------------------------------
from com.cognizant.devops.platformagents.core.BaseAgent import BaseAgent
from datetime import datetime as dateTime2
from dateutil import parser
from itertools import chain

import datetime
import json
import logging.handlers
import base64
import urllib
import requests
import json
import logging
from itertools import chain


class QtestAgent(BaseAgent):
    def process(self):
        baseUrl = self.config.get("baseUrl", None)
        username = self.config.get("username", None)
        password = self.config.get("password", None)
        startFrom = self.config.get("startFrom", '')
        timeStampFormat = self.config.get("timeStampFormat", '')
        extensions = self.config.get('dynamicTemplate', {}).get('extensions', None)
        startFrom = parser.parse(startFrom, ignoretz=True)
        domainName = "InSightsAlmAgent:"
        self.authToken = base64.b64encode(domainName.encode('utf-8'))
        self.token = self.login(self.authToken, username, password, baseUrl)
        authTokenTime = datetime.datetime.now()
        headers = {'Content-Type': 'application/json', "accept": "application/json","Authorization": "bearer "+self.token}
        pagination = ["test-cases", "requirements", "test-runs", "trace-matrix-report", "defects"]
        searchSupportedAlmEntities = ["test-cases", "requirements", "test-runs"]
        self.username , self.password , self.headers , self.baseUrl = username, password, headers, baseUrl
        self.pageSize = self.config.get('almEntityPageSize', 20)
        #In this part we addthe module name where pagination is supported.
        try:
            projectsList = self.getResponse(baseUrl+"/api/v3/projects?assigned=false", 'GET', None, None, None, None, headers)
            almEntities = self.config.get("dynamicTemplate", {}).get("almEntities", None)
            self.historyEntities = self.config.get("dynamicTemplate", {}).get("queryObjectHistory", {})
            self.objectSize = self.historyEntities.get('objectSize', 100)
            if len(projectsList) > 0:
                for projects in projectsList:
                    projectName = projects.get("name", None)
                    projectId = projects.get("id", None)
                    trackingDetails = self.tracking.get(str(projectId),None)
                    if trackingDetails is None:
                        trackingDetails = {}
                        self.tracking[str(projectId)] = trackingDetails
                    if len(almEntities) > 0:
                        entityUpdatedDate = None
                        for entityType in almEntities:
                            page_num = 1
                            page_size = self.pageSize
                            data = []
                            reqIdLatest = list()
                            metadata = self.config.get("dynamicTemplate", {}).get("almEntityMetaData", None)
                            searchApiSupported = (entityType in searchSupportedAlmEntities)
                            almEntityRestDetails = self.almEntityRestDetails(entityType, projectId, baseUrl, pagination, searchApiSupported)
                            entityUpdatedDate = almEntityRestDetails.get('entityUpdatedDate', None)
                            if entityUpdatedDate is not None:
                                startFrom = parser.parse(entityUpdatedDate, ignoretz=True)
                                entityUpdatedDate = startFrom
                            nextPageResponse = True
                            entity_type_available = False
                            reqIdList = trackingDetails.get(entityType, {}).get("entityIdDict", None)
                            restUrl = almEntityRestDetails.get('restUrl', None)
                            searchApiQueryObject = None 
                            if searchApiSupported:
                                restUrl = almEntityRestDetails.get('restUrl', None) + "?pageSize="+str(page_size)
                                lastModifiedDateStr = startFrom.strftime(timeStampFormat)+"+00:00"
                                searchApiQueryObject = { "object_type": entityType, "fields": [ "*" ], "query": "'Last Modified Date' >= '"+lastModifiedDateStr+"'" }
                                print searchApiQueryObject
                            else:
                                restUrl = almEntityRestDetails.get('restUrl', None) + almEntityRestDetails.get('entityType', None)
                                restUrl = restUrl + "?expandProps=true&expandSteps=false&expand=descendants&size=" + str(page_size)
                                restUrl = restUrl + almEntityRestDetails.get('dateTimeStamp', None) + urllib.quote_plus(startFrom.strftime(timeStampFormat)) + "Z"
                            if reqIdList is None:
                                reqIdList = []
                            automatedTestCases = []
                            while nextPageResponse:
                                restApiUrl = restUrl + "&page=" + str(page_num)
                                print restApiUrl + ", Query:   "+json.dumps(searchApiQueryObject)
                                try:
                                    if searchApiSupported:
                                        entityTypeResponse = self.getResponse(restApiUrl, 'POST', None, None, json.dumps(searchApiQueryObject), None, headers)
                                    else:
                                        entityTypeResponse = self.getResponse(restApiUrl, 'GET', None, None, None, None, headers)
                                    #headers = {'Content-Type': 'application/json', 'Authorization': 'bearer ' + self.token}
                                except Exception as ex1:
                                    exceptionMsg = str(ex1)
                                    if "invalid_token" in exceptionMsg and (datetime.datetime.now() - authTokenTime).total_seconds() >= 5:
                                        authTokenTime = datetime.datetime.now()
                                        self.token = self.login(self.authToken, username, password, baseUrl)
                                        headers = {'Content-Type': 'application/json', "accept": "application/json","Authorization": "bearer "+self.token}
                                        logging.warn('Current session has extended.')
                                        continue
                                    nextPageResponse = False
                                    logging.error("ProjectID: " + str(projectId) + " Type: " +str(entityType) + " URL: " + str(restUrl) + "  " + str(ex1))
                                    break
                                if entityType in pagination and "items" in entityTypeResponse and len(entityTypeResponse["items"]) == 0:
                                    break
                                elif entityType in pagination and "items" in entityTypeResponse and len(entityTypeResponse["items"]) > 0:
                                    entityTypeResponse = entityTypeResponse.get("items", {})
                                else:
                                    pass
                                if len(entityTypeResponse) > 0:
                                    entity_type_available = True
                                    try:
                                        for res in entityTypeResponse:
                                            lastUpdated = res.get('last_modified_date', None)
                                            if lastUpdated is not None:
                                                lastUpdated = parser.parse(lastUpdated, ignoretz=True)
                                                if lastUpdated > startFrom:
                                                    if entityUpdatedDate is None or lastUpdated > entityUpdatedDate:
                                                        entityUpdatedDate = lastUpdated
                                                    responseTemplate = almEntities.get(entityType, None)
                                                    if responseTemplate:
                                                        injectData= {}
                                                        injectData['projectName'] = projectName
                                                        injectData['projectId'] = projectId
                                                        injectData['almType'] = entityType
                                                        #EXTRACTION OF JIRA-KEY FROM NAME FIELD IN REQUIREMENTS.
                                                        if entityType == 'requirements':
                                                            if 'name' in res:
                                                                #matchObj = re.match( r'(.*)-(.*?) .*', res.get('name', ''), re.M|re.I)
                                                                #injectData['jiraKey'] = '-'.join(matchObj.group(1, 2))
                                                                #FOR NOW ASSUMING THAT IN NAME FIELD FIRST WORD WILL BE JIRA KEY.
                                                                injectData['jiraKey'] = res.get('name', '').split(' ')[0]
                                                        #EXTRACTION PROPERTY VALUES FROM API RESPONSE.
                                                        _ObjectId = str(res.get('id'))
                                                        if _ObjectId not in reqIdList:
                                                            reqIdList.append(_ObjectId)
                                                        if entityType in self.historyEntities:
                                                            reqIdLatest.append(_ObjectId)
                                                        if 'properties' in res:
                                                            for property in res.get('properties', []):
                                                                injectData[str(property.get('field_name').lower()).replace(' ', '')] = property.get('field_value_name')
                                                        data += self.parseResponse(responseTemplate, res, injectData)
                                                        if entityType == 'test-cases' and injectData.get('type', '') == 'Automation':
                                                            automatedTestCases.append(_ObjectId)
                                                        #FOR COLLECTING DATA BEYOND PARENT/ROOT LEVEL. FUNCTION DEFINITION IS AT THE BOTTOM.
                                                        #self.injectResponseData(data, responseTemplate, res, projectName, projectId, entityType)
                                    except Exception as ex:
                                        nextPageResponse = False
                                        entity_type_available = False
                                        logging.error("ProjectID: " + str(projectId) + " Type: " +str(entityType) + str(ex))
                                        break
                                else:
                                    nextPageResponse = False
                                if searchApiSupported and len(entityTypeResponse) < self.pageSize:
                                    nextPageResponse = False
                                if almEntityRestDetails.get('pagination', False):
                                    if entityType == "defects":
                                        page_size = page_size + self.pageSize
                                    else:
                                        page_num = page_num + 1
                                else:
                                    nextPageResponse = False
                            if entity_type_available and entityUpdatedDate is not None:
                                entityUpdatedDate = entityUpdatedDate.strftime(timeStampFormat)
                                if len(reqIdList) > 0 and entityType in extensions.get('linkedArtifacts', {}).get('almEntities', {}):
                                    trackingDetails[entityType] = {"entityUpdatedDate": entityUpdatedDate, "entityIdDict": reqIdList}
                                else:
                                    trackingDetails[entityType] = {"entityUpdatedDate": entityUpdatedDate}
                            if automatedTestCases:
                                data = data + self.typePropertyhistoryApi(projectId, entityType, automatedTestCases)
                            print "ProjectId: "+str(projectId)+", entity: "+entityType+", DataSize: "+str(len(data))+", url: "+restUrl
                            if len(data) > 0:
                                self.publishToolsData(data, metadata)
                        self.tracking[str(projectId)] = trackingDetails
                        self.updateTrackingJson(self.tracking)
        finally:
            self.logout(self.token, baseUrl)

    def login(self, authToken, username, password, baseUrl):
        headers_token = {'accept': "application/json",'content-type': "application/x-www-form-urlencoded",'authorization': "Basic "+str(authToken)+""}
        payload = "grant_type=password&username="+str(username)+"&password="+str(password)
        tokenResponse = self.getResponse(baseUrl+"/oauth/token", 'POST', None, None, payload, None, headers_token)
        if "error" in tokenResponse:
            logging.error("InValid Credentails")
        return tokenResponse.get("access_token", None)

    def logout(self, token, baseUrl):
        headerTokenRevoke = {"Authorization": "bearer "+str(token)+""}
        tokenResponse = self.getResponse(baseUrl+"/oauth/revoke", 'POST', None, None, None, None, headerTokenRevoke)

    def typePropertyhistoryApi(self, projectId, objectType, objectIdList):
        try:
            toolsHistoryData = list()
            page = 1
            totalPages = 0
            lastPageSize = 0
            pageSize = self.pageSize
            property = self.historyEntities.get(objectType, {}).get("Type")
            objectQuery = self.constructHistoryObjectQuery(objectIdList)
            for _Chunks in objectQuery:
                if _Chunks:
                    nextResponse = True
                    while nextResponse:
                        totalPages, pageSize, lastPageSize, nextResponse, historyResponse = \
                            self.queryObjectHistoryApi(projectId, objectType, objectQuery=_Chunks, page=page,
                                                       pageSize=pageSize if page != totalPages else lastPageSize, testCaseCount=len(objectIdList))
                        if 'items' in historyResponse and historyResponse['items']:
                            changeHistory = historyResponse.get('items')
                            for _Iter in changeHistory:
                                changes = _Iter['changes']
                                for _FieldChange in changes:
                                    fieldName = _FieldChange['field']
                                    newValue = _FieldChange['new_value']
                                    if fieldName == 'Type' and newValue == property['newValue']:
                                        data = {"projectId": projectId, "almType": objectType, "id": _Iter['linked_object']['object_id'], "automationTime": _Iter['created'][:-6]}
                                        toolsHistoryData.append(data)
                            page = page + 1
                        else:
                            nextResponse = False
            mappedHistoryData = self.mapToPair(toolsHistoryData)
            for _Iter in mappedHistoryData:
                mappedHistoryData[_Iter] = self.listSplitter(mappedHistoryData[_Iter], property.get('limit', 1))
            return list(chain.from_iterable(mappedHistoryData.values()))
        except Exception as err:
            logging.error(err)

    @staticmethod
    def mapToPair(data):
        try:
            dataPair = dict()
            for _Iter in data:
                _Id = _Iter['id']
                if _Id in dataPair:
                    dataPair.get(_Id).append(_Iter)
                else:
                    dataPair[_Id] = [_Iter, ]
            return dataPair
        except Exception as err:
            logging.error(err)

    @staticmethod
    def _ConstructHistoryObjectQuery(objectIdList):
        objectQuery = str()
        objectIdListLen = len(objectIdList)
        for _iter in range(0, objectIdListLen):
            _ObjectId = objectIdList[_iter]
            objectQuery += '\'id\' = \'' + _ObjectId + '\''
            if _iter != objectIdListLen - 1:
                objectQuery += ' or '
        return objectQuery

    def constructHistoryObjectQuery(self, objectIdList):
        if len(objectIdList) > self.objectSize:
            objectQueryList = list()
            chunks = [objectIdList[_Iter: _Iter + self.objectSize] for _Iter in range(0, len(objectIdList), self.objectSize)]
            for _Iter in chunks:
                objectQueryList.append(self._ConstructHistoryObjectQuery(_Iter))
            return objectQueryList
        else:
            return [self._ConstructHistoryObjectQuery(objectIdList), ]

    @staticmethod
    def listSplitter(dataList, limit=1, reverse=True):
        if reverse:
            limit = -limit
        return dataList[:limit] if limit >= 0 else dataList[limit:]

    def queryObjectHistoryApi(self, projectId, objectType, fields=None, objectQuery=None, query=None, page=None, pageSize=None, testCaseCount=0):
        try:
            totalPages = 0
            lastPageSize = 0
            pageSize = self.pageSize
            headers = {'Content-Type': 'application/json', 'Authorization': 'bearer ' + self.token}
            data = {"object_type": objectType, "fields": fields if fields else ["*"], "object_query": objectQuery if objectQuery else "", "query": query if query else ""}
            url = self.baseUrl + "/api/v3/projects/" + str(projectId) + ("/histories" if not page else "/histories?page={0}&pageSize={1}".format(page, pageSize))
            response = requests.post(url, data=json.dumps(data), headers=headers, verify=False)
            if response.status_code == 500:
                newResponse = requests.post(self.baseUrl + "/api/v3/projects/" + str(projectId) + "/histories?page=1&pageSize=1", data=json.dumps(data), headers=headers, verify=False)
                if newResponse.status_code == 200:
                    total = json.loads(newResponse.content).get('total')
                    if 0 < total <= 100:
                        currentResponse = requests.post(self.baseUrl + "/api/v3/projects/" + str(projectId) + "/histories?page=1&pageSize=" + str(total - testCaseCount), data=json.dumps(data), headers=headers, verify=False).content
                        return totalPages, pageSize, lastPageSize, False, json.loads(currentResponse)
                    else:
                        totalPages = total // 100 + 1
                        lastPageSize = total % 100
                        currentResponse = requests.post(self.baseUrl + "/api/v3/projects/" + str(projectId) + "/histories?page=1&pageSize=" + str(100), data=json.dumps(data), headers=headers, verify=False).content
                        return totalPages, pageSize, lastPageSize, True, json.loads(currentResponse)
            else:
                return totalPages, pageSize, lastPageSize, True, json.loads(response.content)

        except Exception as err:
            logging.error(err)

    def filterDataStructure(self, almType, responseObj):
        objs = {almType : True}
        for key, value in objs.iteritems():
            if value == True:
                return responseObj.get(key, None)

    def almEntityRestDetails(self, entityType, projectId, baseUrl, paginationList, searchApiSupported=False):
        urlExtension = {
                        "trace-matrix-report": "requirements/trace-matrix-report",
                        "defects": "defects/last-change"
                        }
        restUrl = baseUrl + "/api/v3/projects/" + str(projectId) + "/"
        if searchApiSupported:
            restUrl = restUrl + 'search'
        entityRestDetails = {}
        entityRestDetails['restUrl'] = restUrl
        entityRestDetails['entityType'] = entityType
        entityRestDetails['pagination'] = False
        entityRestDetails['dateTimeStamp'] = '&startTime='
        entityRestDetails['entityUpdatedDate'] = self.tracking.get(str(projectId), {}).get(entityType, {}).get("entityUpdatedDate", None)
        if entityType in urlExtension:
            entityRestDetails['entityType'] = str(urlExtension.get(entityType, ""))
        if entityType in paginationList:
            entityRestDetails['pagination'] = True
        return entityRestDetails

    def scheduleExtensions(self):
        extensions = self.config.get('dynamicTemplate', {}).get('extensions', None)
        if extensions:
            linkedArtifacts = extensions.get('linkedArtifacts', None)
            if linkedArtifacts:
                self.registerExtension('linkedArtifacts', self.retrieveLinkedArtifacts, linkedArtifacts.get('runSchedule'))
            requirementMatrix = extensions.get('requirementMatrix', None)
            if requirementMatrix:
                self.registerExtension('requirementMatrix', self.retrieveRequirementMatrix, requirementMatrix.get('runSchedule'))

    def retrieveLinkedArtifacts(self):
        try:
            token = self.login(self.authToken, self.username , self.password , self.baseUrl)
            headers = {"accept": "application/json","Authorization": "bearer "+token}
            linkedArtifacts = self.config.get('dynamicTemplate', {}).get('extensions', {}).get('linkedArtifacts', None)
            trackingDetails = self.tracking
            try:
                for project in trackingDetails:
                    data = []
                    for almEntity in trackingDetails.get(str(project), {}):
                        if almEntity in linkedArtifacts.get('almEntities', None):
                            projectTrackingDetails = trackingDetails.get(str(project))
                            entityIdDict = projectTrackingDetails.get(almEntity, {}).get('entityIdDict', None)
                            if entityIdDict is None:
                                continue
                            try:
                                dictIsNotEmpty = True
                                start = 0
                                end = self.pageSize
                                while dictIsNotEmpty:
                                    linkedArtifactUrl = "{}/api/v3/projects/{}/linked-artifacts?type={}&ids={}".format(self.baseUrl, str(project), almEntity, ','.join(entityIdDict[start:end]))
                                    print linkedArtifactUrl
                                    entityTypeResponse = self.getResponse(linkedArtifactUrl, 'GET', None, None, None, None, headers)
                                    for res in entityTypeResponse:
                                        parentId = res.get('id', None)
                                        if len(res.get('objects', [])) > 0:
                                            injectData = {}
                                            injectData['id'] = parentId
                                            injectData['projectId'] = int(project)
                                            injectData['almType'] = 'linked-objects'
                                            injectData['almParentType'] = almEntity
                                            for object in res.get('objects', None):
                                                almType = (object.get('self', None).split('/')[-2]).replace('-', '')
                                                if almType not in injectData:
                                                    injectData[almType] = [object.get('id')]
                                                else:
                                                    injectData[almType].append(object.get('id', None))
                                            data.append(injectData)
                                    start = end
                                    end = end + self.pageSize
                                    if len(entityIdDict[start:end]) == 0:
                                        dictIsNotEmpty = False
                            finally:
                                self.tracking.get(str(project)).get(almEntity, {}).pop('entityIdDict')
                    if len(data) > 0:
                        metadata = self.config.get("dynamicTemplate", {}).get('extensions', {}).get('linkedArtifacts', {}).get("almEntityMetaData", None)
                        self.publishToolsData(data, metadata)
                        self.updateTrackingJson(self.tracking)
            except Exception as ex1:
                logging.error("Error in retrieveLinkedArtifacts which is part of extensions in " + str(ex1))
        finally:
            self.logout(token, self.baseUrl)

    def retrieveRequirementMatrix(self):
        dataMatrix = []
        metadata = self.config.get("dynamicTemplate", {}).get('extensions', {}).get('requirementMatrix', {}).get("almEntityMetaData", None)
        try:
            token = self.login(self.authToken, self.username , self.password , self.baseUrl)
            headers = {"accept": "application/json","Authorization": "bearer "+token}
            trackingDetails = self.tracking
            for project in trackingDetails:
                almEntityRestDetails = self.almEntityRestDetails("trace-matrix-report", project, self.baseUrl, ['trace-matrix-report'])
                nextPageResponse = True
                page_num = 1
                page_size = self.pageSize
                while nextPageResponse:
                    restUrl = almEntityRestDetails.get('restUrl', None) + almEntityRestDetails.get('entityType', None) + "?page=" + str(page_num) + "&size=" + str(page_size)
                    try:
                        entityTypeResponse = self.getResponse(restUrl, 'GET', None, None, None, None, headers)
                        if entityTypeResponse.__len__() > 0:
                            for res in entityTypeResponse:
                                traceMatrixReport = res.get("requirements", {})
                                for matrix in traceMatrixReport:
                                    injectData= {}
                                    if "testcases" in matrix:
                                        injectData['modulesId'] = res.get('id', None)
                                        injectData['projectId'] = int(project)
                                        injectData['almType'] = "trace-matrix-report"
                                        injectData['testcases'] = matrix.get("testcases", None)
                                        injectData['linkedTestCases'] = matrix.get("linked-testcases", None)
                                        injectData['id'] = matrix.get("id", None)
                                        dataMatrix.append(injectData)
                        else:
                            nextPageResponse = False
                    except Exception as urlError:
                        nextPageResponse = False
                        break
                    page_num = page_num + 1
        finally:
            self.logout(token, self.baseUrl)
        if len(dataMatrix) > 0:
            self.publishToolsData(dataMatrix, metadata)

    '''
    def injectResponseData(self, data, responseTemplate, res, projectName, projectId, entityType):
        injectData= {}
        injectData['projectName'] = projectName
        injectData['projectId'] = projectId
        injectData['almType'] = entityType
        if entityType == 'requirements':
            if 'name' in res:
                injectData['jiraKey'] = res.get('name', '').split(' ')[0]
                combinedProperty = {}
                if 'properties' in res:
                    for property in res.get('properties', []):
                        injectData[property.get('field_name')] = property.get('field_value')
        if "children" in res:
            for child in res.get('children', None):
                data += self.parseResponse(responseTemplate, child, injectData)
                self.injectResponseData(data, responseTemplate, child.get('children', None), projectName, projectId, entityType)
        data += self.parseResponse(responseTemplate, res, injectData)
    '''
if __name__ == "__main__":
    QtestAgent()